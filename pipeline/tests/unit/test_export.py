"""REQ-EXP-1.1-1.4 and REQ-ING-PII: validated, deterministic, atomic exports."""

from __future__ import annotations

import json
import random

import duckdb
import pytest
from helpers import mk

from undead311.detect.cases import cases_from_table
from undead311.detect.core import detect
from undead311.detect.params import DEFAULT
from undead311.export.writers import (
    ContractError,
    ExportContext,
    build_payloads,
    canonical_json,
    data_version,
    export_all,
    snapshot_date,
    validate,
    write_duckdb_atomic,
)
from undead311.fixtures import load_test_town
from undead311.ingest.clean import clean, ids_by_reason
from undead311.ingest.crosswalk import apply_crosswalk


def town_inputs(shuffle_seed: int | None = None):
    con = duckdb.connect()
    load_test_town(con)
    apply_crosswalk(con)
    report = clean(con)
    cases = cases_from_table(con, "cases_clean")
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(cases)
    ctx = ExportContext(
        data_version="2026-11-12+abc1234+deadbeef", run_time="2026-11-13T00:00:00Z",
        row_counts={"cases_clean": report.kept}, exclusion_counts=report.counts, excluded_ids=ids_by_reason(con),
        segments="missing", stats_status={"calibration_warning": None}, data_end="2026-11-12",
    )  # fmt: skip
    return detect(cases), {c.id: c for c in cases}, ctx


def read_all(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*.json"))}


def test_req_exp_1_1_every_file_validates_and_status_is_written_last(tmp_path):
    """REQ-EXP-1.1: all engine files validate against /schemas/; status.json is the last file written."""
    result, cases, ctx = town_inputs()
    written = export_all(result, cases, tmp_path, ctx)
    assert written[-1].name == "status.json"
    names = {str(p.relative_to(tmp_path)) for p in written}
    assert {"zombies.json", "incidents.json", "points.json", "exclusions.json", "separate_deaths.json",
            "repeat_offenders.json", "bulk_closures.json", "status.json"} <= names  # fmt: skip
    assert any(n.startswith("cards/") for n in names)
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["headline_count"] == 16 and status["source_unknown_count"] == 2 and status["sensitivity_count"] == 2
    z = json.loads((tmp_path / "zombies.json").read_text())
    assert len(z["zombies"]) == 20 and z["data_version"] == ctx.data_version


def test_req_exp_1_2_records_are_sorted_by_stable_ids(tmp_path):
    """REQ-EXP-1.2: zombie_id = incident_id:resurrection_id, sorted; points are parallel arrays of equal length."""
    result, cases, ctx = town_inputs()
    p = build_payloads(result, cases, ctx)
    ids = [z["zombie_id"] for z in p["zombies.json"]["zombies"]]
    assert ids == sorted(ids) and ids[0] == "101099001001:101099001002"
    pts = p["points.json"]
    assert pts["n"] == len(ids) and all(len(pts[k]) == pts["n"] for k in ("id", "lat", "lon", "tier", "family", "year"))
    assert pts["id"] == ids


def test_req_exp_1_3_two_runs_and_shuffled_input_give_byte_identical_files(tmp_path):
    """REQ-EXP-1.3 and P4 part 2: same input, or the same rows in another order, gives identical bytes."""
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    export_all(*town_inputs()[:2], a, town_inputs()[2])
    export_all(*town_inputs()[:2], b, town_inputs()[2])
    result, cases, ctx = town_inputs(shuffle_seed=7)
    export_all(result, cases, c, ctx)
    assert read_all(a) == read_all(b) == read_all(c)


def test_req_exp_1_1_an_invalid_record_is_refused_before_anything_is_written(tmp_path):
    """REQ-EXP-1.1: a payload that breaks its schema stops the export; the folder stays empty."""
    result, cases, ctx = town_inputs()
    bad = result.zombies[0].__class__(**{**result.zombies[0].__dict__, "confidence": 1.5})
    result.zombies[0] = bad
    with pytest.raises(ContractError, match="zombies"):
        export_all(result, cases, tmp_path, ctx)
    assert list(tmp_path.iterdir()) == []


def test_req_exp_1_1_validate_names_the_failing_file():
    """REQ-EXP-1.1: error text names the schema and the path."""
    with pytest.raises(ContractError, match=r"status: .*"):
        validate("status", {"data_version": "x"})


def test_req_ing_pii_1_cards_and_notes_carry_scrubbed_text(tmp_path):
    """REQ-ING-PII.1: closure text and Skeptic notes in exports never carry phones, emails or names."""
    cs = [mk("A", 0, 1, text="Closed. Called by Maria Lopez 617-555-0100 or m@x.org"), mk("R", 5, text="per John Smith")]
    result = detect(cs)
    from dataclasses import replace

    result.zombies[0] = replace(result.zombies[0], skeptic_notes="Mr. Brown at 6175550100 said so")
    ctx = ExportContext(data_version="v", run_time="t")
    export_all(result, {c.id: c for c in cs}, tmp_path, ctx)
    blob = "".join(p.read_text() for p in tmp_path.rglob("*.json"))
    for secret in ("Maria", "Lopez", "555-0100", "m@x.org", "Brown", "6175550100", "John Smith"):
        assert secret not in blob
    assert "[removed]" in blob


def test_req_exp_1_2_data_version_has_snapshot_sha_and_parameter_hash(tmp_path):
    """REQ-EXP-1.2: `<snapshot date>+<short sha>+<parameter hash>`; the hash changes with a parameter."""
    snap = tmp_path / "SNAPSHOT.md"
    snap.write_text("# Data snapshot\n\nDownloaded: 2026-11-12 (source: x)\n")
    assert snapshot_date(snap) == "2026-11-12" and snapshot_date(tmp_path / "none.md") == "unknown"
    from dataclasses import replace

    v1 = data_version("2026-11-12", DEFAULT)
    v2 = data_version("2026-11-12", replace(DEFAULT, RADIUS_M=50))
    assert v1.startswith("2026-11-12+") and v1.split("+")[2] != v2.split("+")[2] and v1.split("+")[1] == v2.split("+")[1]


def test_req_exp_1_4_duckdb_file_is_written_atomically(tmp_path):
    """REQ-EXP-1.4: a build that fails leaves the previous file untouched and no temporary file behind."""
    final = tmp_path / "undead311.duckdb"
    write_duckdb_atomic(final, lambda con: con.execute("create table t as select 1 as x"))
    assert duckdb.connect(str(final), read_only=True).execute("select x from t").fetchone() == (1,)

    def boom(con):
        con.execute("create table t2 as select 2 as y")
        raise RuntimeError("stage failed")

    with pytest.raises(RuntimeError):
        write_duckdb_atomic(final, boom)
    con = duckdb.connect(str(final), read_only=True)
    assert [r[0] for r in con.execute("show tables").fetchall()] == ["t"]
    assert [p.name for p in tmp_path.iterdir()] == ["undead311.duckdb"]


def test_req_exp_1_3_canonical_json_is_key_sorted_and_compact():
    """REQ-EXP-1.3: sorted keys, no spaces, one trailing newline."""
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}\n'


def test_req_exp_1_web_contract_shard_names_resurrection_date_and_card_partial_flag(tmp_path):
    """REQ-EXP-1.1-1.2 (ops#12): shards are cards/<slug(neighborhood)>-<re-report year>.json, zombies carry
    resurrection_date, cards carry confidence_partial, and points.year is the re-report year."""
    result, cases, ctx = town_inputs()
    p = build_payloads(result, cases, ctx)
    z = {x["zombie_id"]: x for x in p["zombies.json"]["zombies"]}
    first = z["101099001001:101099001002"]
    assert first["resurrection_date"] == "2024-03-26"
    shard = "cards/dorchester-2024.json"
    assert shard in p
    card = next(c for c in p[shard]["cards"] if c["zombie_id"] == "101099001001:101099001002")
    assert card["resurrection_date"] == "2024-03-26" and card["confidence_partial"] is True
    idx = p["points.json"]["id"].index("101099001001:101099001002")
    assert p["points.json"]["year"][idx] == 2024


def test_req_exp_1_1_card_original_is_the_closing_member_that_the_label_and_gap_come_from(tmp_path):
    """REQ-EXP-1.1, ZD step 2 (ops#32): a two-member incident shows the latest-closing member as the original, so the
    closure text, the close time and the gap on the card agree."""
    cs = [
        mk("A", 0, 1, text="Closed early", label="resolved"),
        mk("B", 0.5, 3, text="Closed last", label="made_safe_temporary"),
        mk("R", 10),
    ]
    result = detect(cs)
    (z,) = result.zombies
    assert z.member_ids == ("A", "B") and z.coroner_label == "made_safe_temporary"
    ctx = ExportContext(data_version="v", run_time="t")
    card = next(v for k, v in build_payloads(result, {c.id: c for c in cs}, ctx).items() if k.startswith("cards/"))["cards"][0]
    assert card["original"]["id"] == "B" and card["original"]["closure_text"] == "Closed last"
    assert card["original"]["close_time"].startswith("2024-03-07")  # day 3 after 2024-03-04
    assert abs(card["gap_days"] - 7.0) < 1e-6  # R opens on day 10, the incident closes on day 3


def test_req_det_pf_planned_followups_are_counted_in_status(tmp_path):
    """REQ-DET-PF, ZD output `is_planned_followup` (ops#33): follow-ups are not zombies; status.json counts them."""
    cs = [mk("A", 0, 1, label="made_safe_temporary"), mk("R", 5, source="Employee Generated")]
    result = detect(cs)
    assert not result.zombies and len(result.planned_followups) == 1
    export_all(result, {c.id: c for c in cs}, tmp_path, ExportContext(data_version="v", run_time="t"))
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["planned_followup_count"] == 1 and status["headline_count"] == 0
    assert all(not z["is_planned_followup"] for z in json.loads((tmp_path / "zombies.json").read_text())["zombies"])
