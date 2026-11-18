"""fix/fulldata-2: per-tier baselines and distance bands (REQ-STAT-POP, REQ-STAT-BAND), the Coroner leading-phrase labeler
(REQ-COR-PHRASE), the department crosswalk (REQ-ING-DEPT), sharded exports (REQ-EXP-SIZE.2-4), the exports release
(REQ-OPS-PUBLISH) and the snapshot date of `data_version` (REQ-EXP-1.2)."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tarfile
from pathlib import Path

import duckdb
import pytest
from helpers import day, mk, payload_zombies, read_zombies
from hypothesis import given
from hypothesis import strategies as st
from test_export import town_inputs

from undead311.coroner.eval import evaluate_random
from undead311.coroner.join import ALLOWED_LABELS, load_template_labels
from undead311.coroner.phrases import phrase_label
from undead311.coroner.templates import mask_template
from undead311.detect.core import detect
from undead311.export.writers import (
    FILE_BUDGET_GZIP_BYTES,
    FIRST_VIEW_RAW_CEILING_BYTES,
    PayloadBudgetExceeded,
    build_payloads,
    check_file_budget,
    check_raw_ceiling,
    export_all,
    gzip_size,
    schema_name,
)
from undead311.ingest.departments import apply_departments, department_report, read_departments
from undead311.pipeline import owns_output, run_pipeline
from undead311.stats.baseline import BaselineModel
from undead311.stats.tiers import BAND_NAMES, band_of, band_shares, tier_excess_rows, tier_models

REPO = Path(__file__).resolve().parents[3]

# ---- REQ-STAT-POP: a tier's baseline counts only that tier's population ---------------------------------------------------


def spot_town(city_reports: int, resident_reports: int):
    """One spot: an original closed on day 1, then reports at 100-day steps. Some are city crew (legacy Employee Generated)."""
    cs = [mk("A0", 0, 1)]
    n = 0
    for _ in range(resident_reports):
        n += 1
        cs.append(mk(f"R{n}", 100 + n * 100, None))
    for _ in range(city_reports):
        n += 1
        cs.append(mk(f"C{n}", 100 + n * 100, None, source="City Worker App"))
    return cs


def test_req_stat_pop_1_the_headline_baseline_ignores_city_crew_reports():
    """Same spot, same reports, but they are city crew reports: the pooled model counts them, the headline population does not."""
    cs = spot_town(city_reports=6, resident_reports=0) + [mk(f"Z{i}", 10 + i, 11 + i, x=500) for i in range(0)]
    by = {c.id: c for c in cs}
    result = detect(cs)
    pooled = BaselineModel(by, result, data_end=day(1200))
    inc = next(i for i in result.incidents if "A0" in i.member_ids)
    tms = {t.tag: t for t in tier_models(by, result, data_end=day(1200))}
    p_pooled = pooled.p(inc)
    assert p_pooled is not None and p_pooled > 0
    head = tms["headline"].model
    assert inc.incident_id not in {i.incident_id for i in head.incidents} or head.p(inc) in (None, 0.0)
    city = tms["city_rereport"].model
    assert city.population is not None and city.estimate(inc).p is not None


def test_req_stat_pop_1_each_tier_has_its_own_rows_and_they_are_never_pooled():
    cs = spot_town(city_reports=3, resident_reports=3)
    by = {c.id: c for c in cs}
    result = detect(cs)
    rows = tier_excess_rows(tier_models(by, result, data_end=day(1500)), boot=50)
    tiers = {r.tier_set for r in rows}
    assert tiers <= {"headline", "source_unknown", "city_rereport", "sensitivity"} and "all" not in tiers
    assert all(r.kind in {"department", "family", "neighborhood", "tier"} for r in rows)
    # the tier rows are separate rows: no row sums two tiers
    per_tier = [r for r in rows if r.kind == "tier"]
    assert len({r.tier_set for r in per_tier}) == len(per_tier)


@given(st.floats(0, 200, allow_nan=False), st.floats(0, 200, allow_nan=False))
def test_req_stat_band_1_a_distance_belongs_to_exactly_one_band(a, b):
    for d in (a, b):
        assert 0 <= band_of(d) < len(BAND_NAMES)
    if a <= b:
        assert band_of(a) <= band_of(b)


def test_req_stat_band_1_band_shares_add_up_to_one_per_original():
    cs = [mk("A0", 0, 1), mk("R1", 150, x=3), mk("R2", 300, x=12), mk("R3", 450, x=25, segment="s1"), mk("R4", 600)]
    by = {c.id: c for c in cs}
    result = detect(cs)
    for tm in tier_models(by, result, data_end=day(1500)):
        for share in band_shares(tm.model).values():
            assert share.sum() == pytest.approx(1.0) and (share >= 0).all()


# ---- REQ-COR-PHRASE ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Case Closed. Closed date : 2019-01-01 10:00:00 Case Resolved replaced lamp. vm/jm", "resolved"),
        ("Case Closed. Case Noted The picture and the address do not match.", "invalid"),
        ("Duplicate of Existing Case Duplicate of case 101001393697", "duplicate"),
        ("Case Closed Case Resolved Location has been made safe. This sidewalk will be referred for permanent repair.", "made_safe_temporary"),
        ("Case Closed. Case Noted added to patch list", "planned_followup"),
        ("Case Closed. Case Noted we are closing out backlogged service requests, old service request", "bulk_backlog"),
        ("Case Closed. Case Invalid", "invalid"),
        ("Case Closed. Case Referred to External Agency reported to MBTA", "referred"),
    ],
)
def test_req_cor_phrase_1_leading_phrases_give_the_expected_label(text, label):
    assert phrase_label(mask_template(text)) == label


def test_req_cor_phrase_1_a_text_no_rule_places_stays_unlabeled():
    assert phrase_label(mask_template("")) is None and phrase_label(mask_template("zzz qqq")) is None


@given(st.text(max_size=200))
def test_req_cor_phrase_1_output_is_deterministic_and_always_an_allowed_label(text):
    first = phrase_label(mask_template(text))
    assert first == phrase_label(mask_template(text)) and (first is None or first in ALLOWED_LABELS)


def test_req_cor_phrase_3_the_random_draw_agrees_with_the_coroner_and_covers_every_row():
    """The 200 random full-data closures (seed 311) labeled by the Coroner agent: the whole pipeline rule agrees on at least 85%,
    and no row is left unlabeled."""
    rows = list(csv.DictReader((REPO / "data" / "labels" / "coroner_random200.csv").open(encoding="utf-8")))
    assert len(rows) == 200
    rep = evaluate_random(load_template_labels(REPO / "data" / "labels" / "coroner_labels.csv"), rows)
    assert rep.unlabeled == 0 and rep.correct / rep.n >= 0.85


# ---- REQ-ING-DEPT -----------------------------------------------------------------------------------------------------------


def test_req_ing_dept_1_every_row_has_a_source_a_known_status_and_each_raw_value_appears_once():
    rows = read_departments()
    keys = [(r["system"], r["department_raw"]) for r in rows]
    assert len(keys) == len(set(keys)) and all(r["source"].strip() for r in rows)
    assert {r["status"] for r in rows} == {"official", "mapped", "as_published", "excluded", "flagged"}
    by = {r["department_raw"]: r for r in rows if r["system"] == "legacy"}
    # owner decisions 2026-11-16: named codes, codes kept as published, and the test queue
    assert [by[c]["department_name"] for c in ("BHA", "ONS", "DND")] == [
        "Boston Housing Authority", "Office of Neighborhood Services", "Department of Neighborhood Development"]
    assert {by[c]["status"] for c in ("GEN", "GRNi", "ECON")} == {"as_published"} and by["Test"]["status"] == "excluded"
    # every legacy code with in-scope cases is resolved; only Temp (2 raw rows, none in scope) stays flagged
    assert [r["department_raw"] for r in rows if r["system"] == "legacy" and r["status"] == "flagged"] == ["Temp"]


def test_req_ing_dept_1_legacy_codes_and_new_system_names_become_one_key_and_flagged_ones_are_reported():
    con = duckdb.connect()
    con.execute("create table t(system varchar, department varchar, n int)")
    con.executemany("insert into t values (?,?,?)", [
        ("legacy", "PWDx", 1), ("new", "Public Works Department (PWD)", 2), ("new", "Boston Transportation Department (BTD)", 3),
        ("legacy", "BTDT", 4), ("new", "Eversource", 5), ("legacy", "NOPE", 6), ("new", None, 7),
    ])  # fmt: skip
    apply_departments(con, "t")
    got = dict(con.execute("select n, department from t").fetchall())
    assert got[1] == got[2] == "PWDx" and got[3] == got[4] == "BTDT" and got[5] == "Eversource" and got[6] == "NOPE" and got[7] is None
    rep = department_report(con, "t")
    assert rep.flagged == {"new:Eversource": 1} and rep.unlisted == {"legacy:NOPE": 1} and rep.missing == 1


# ---- REQ-EXP-SIZE.2-4 -------------------------------------------------------------------------------------------------------


def test_req_exp_size_2_the_budget_is_gzip_and_the_raw_ceiling_is_separate():
    assert gzip_size(b" " * 5_000_000) < 20_000  # a spaced-out file is small on the wire
    check_raw_ceiling({"points.json": FIRST_VIEW_RAW_CEILING_BYTES})
    with pytest.raises(PayloadBudgetExceeded, match="raw ceiling"):
        check_raw_ceiling({"points.json": FIRST_VIEW_RAW_CEILING_BYTES + 1})


def test_req_exp_size_3_a_file_over_the_gzip_budget_is_refused_and_a_big_raw_file_that_compresses_is_not():
    check_file_budget({"zombies/a-2020.json": FILE_BUDGET_GZIP_BYTES})
    with pytest.raises(PayloadBudgetExceeded, match="zombies/a-2020.json"):
        check_file_budget({"zombies/a-2020.json": FILE_BUDGET_GZIP_BYTES + 1})


def test_req_exp_size_3_zombies_and_incidents_are_sharded_and_every_zombie_is_in_exactly_one_shard(tmp_path):
    result, cases, ctx = town_inputs()
    written = export_all(result, cases, tmp_path, ctx)
    names = {p.relative_to(tmp_path).as_posix() for p in written}
    assert "zombies.json" not in names and "incidents.json" not in names
    zs = read_zombies(tmp_path)
    assert [z["zombie_id"] for z in zs] == sorted({z.zombie_id for z in result.zombies})
    index = json.loads((tmp_path / "zombies" / "index.json").read_text())
    assert sum(s["n"] for s in index["shards"]) == len(zs)
    for s in index["shards"]:  # the shard key names the neighborhood and the re-report year, as the card shards do
        rows = json.loads((tmp_path / "zombies" / f"{s['shard']}.json").read_text())["zombies"]
        assert len(rows) == s["n"] and {r["resurrection_date"][:4] for r in rows} == {str(s["year"])}
    assert [p for p in names if p.startswith("incidents/") and p != "incidents/index.json"]


def test_req_exp_size_4_points_json_is_the_headline_tier_and_the_other_tiers_are_their_own_files():
    result, cases, ctx = town_inputs()
    p = build_payloads(result, cases, ctx)
    assert set(p["points.json"]["tier"]) == {"headline"}
    for tier in ("source_unknown", "city_rereport", "sensitivity"):
        assert set(p[f"points/{tier}.json"]["tier"]) <= {tier}
    total = sum(p[k]["n"] for k in ("points.json", "points/source_unknown.json", "points/city_rereport.json", "points/sensitivity.json"))
    assert total == len(payload_zombies(p))
    assert len(p["points.json"]["date"]) == p["points.json"]["n"]  # the time-lapse needs no zombie shard


def test_req_exp_size_3_districts_and_chain_first_card_come_with_the_export():
    result, cases, ctx = town_inputs()
    p = build_payloads(result, cases, ctx)
    heads = [z for z in result.zombies if z.tier == "headline" and z.district]
    assert sum(d["count"] for d in p["districts.json"]["districts"]) == len(heads)
    ids = {z.zombie_id for z in result.zombies if z.tier == "headline"}
    for c in p["repeat_offenders.json"]["repeat_offenders"]:
        assert c["first_zombie_id"] in ids | {None}


def test_req_exp_size_3_schema_names_and_ownership_cover_the_sharded_files():
    assert schema_name("zombies/a-2020.json") == "zombies" and schema_name("zombies/index.json") == "shard_index"
    assert schema_name("incidents/a-2020.json") == "incidents" and schema_name("points/city_rereport.json") == "points"
    for rel in ("zombies/a-2020.json", "incidents/index.json", "points/sensitivity.json", "districts.json", "zombies.json", "incidents.json"):
        assert owns_output(rel), rel
    assert not owns_output("frozen/points.json")


# ---- REQ-EXP-1.2 (item h) ---------------------------------------------------------------------------------------------------


def test_req_exp_1_2_data_version_takes_its_date_from_the_snapshot_file_it_is_given(tmp_path):
    """The date comes from the snapshot file passed to run_pipeline, never from the checkout's own data/SNAPSHOT.md."""
    snap = tmp_path / "OTHER-SNAPSHOT.md"
    snap.write_text("# Data snapshot\n\nDownloaded: 2031-02-03 (source: test)\n")
    rep = run_pipeline(sample=True, out_dir=tmp_path / "out", work_dir=tmp_path / "data", snapshot_md=snap, grid=False,
                       run_time="2031-02-04T00:00:00Z")  # fmt: skip
    assert rep.data_version.startswith("2031-02-03+")
    assert json.loads((tmp_path / "out" / "status.json").read_text())["data_version"] == rep.data_version
    repo_date = (REPO / "data" / "SNAPSHOT.md").read_text().split("Downloaded:")[1].split()[0]
    assert repo_date != "2031-02-03" and not rep.data_version.startswith(repo_date)


# ---- REQ-OPS-PUBLISH ---------------------------------------------------------------------------------------------------------

_spec = importlib.util.spec_from_file_location("exports_release", REPO / "pipeline" / "scripts" / "exports_release.py")
er = importlib.util.module_from_spec(_spec)
sys.modules["exports_release"] = er
_spec.loader.exec_module(er)


def make_export(folder: Path, **status) -> Path:
    result, cases, ctx = town_inputs()
    export_all(result, cases, folder, ctx)
    s = json.loads((folder / "status.json").read_text())
    s.update({"dataset": "full", **status})
    (folder / "status.json").write_text(json.dumps(s))
    return folder


def test_req_ops_publish_1_pack_and_unpack_round_trip_keeps_frozen_files_and_puts_status_last(tmp_path):
    src = make_export(tmp_path / "exports" / "r1")
    archive, digest = er.pack("r1", src, tmp_path / "rel")
    dest = tmp_path / "site" / "data"
    (dest / "frozen").mkdir(parents=True)
    (dest / "frozen" / "points.json").write_text("judging snapshot")
    (dest / "zombies.json").write_text("old one-piece file")  # owned and retired: swapped out
    (dest / "keep.txt").write_text("not ours")
    manifest = er.unpack(archive, digest, dest)
    assert manifest["run_id"] == "r1" and (dest / "frozen" / "points.json").read_text() == "judging snapshot"
    assert not (dest / "zombies.json").exists() and (dest / "keep.txt").exists()
    for f in src.rglob("*.json"):
        assert (dest / f.relative_to(src)).read_bytes() == f.read_bytes()
    with tarfile.open(archive) as tar:
        assert tar.getnames()[0] == "MANIFEST.json" and tar.getnames()[-1] == "status.json"
    assert er.pack("r1", src, tmp_path / "rel2")[0].read_bytes()[10:] == archive.read_bytes()[10:]  # same files, same bytes (after the header time)


def test_req_ops_publish_1_a_dry_run_or_failed_export_is_never_packed(tmp_path):
    with pytest.raises(er.ExportsError, match="DRY RUN ONLY"):
        er.pack("r", make_export(tmp_path / "a", anomalies=["DRY RUN ONLY, over the first-view budget: x"]), tmp_path / "o")
    with pytest.raises(er.ExportsError, match="ok: true"):
        er.pack("r", make_export(tmp_path / "b", ok=False), tmp_path / "o")
    with pytest.raises(er.ExportsError, match="missing"):
        er.pack("r", tmp_path / "nothing", tmp_path / "o")


def test_req_ops_publish_2_unpack_refuses_a_bad_hash_unsafe_paths_and_files_it_does_not_own(tmp_path):
    src = make_export(tmp_path / "e")
    archive, _digest = er.pack("r1", src, tmp_path / "rel")
    bad = tmp_path / "bad.sha256"
    bad.write_text("0" * 64 + "  x\n")
    with pytest.raises(er.ExportsError, match="mismatch"):
        er.unpack(archive, bad, tmp_path / "d1")
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        info = tarfile.TarInfo("../escape.json")
        info.size = 2
        import io

        tar.addfile(info, io.BytesIO(b"{}"))
    sha = tmp_path / "evil.sha256"
    sha.write_text(f"{er.sha256_file(evil)}  evil\n")
    with pytest.raises(er.ExportsError, match="unsafe"):
        er.unpack(evil, sha, tmp_path / "d2")
    assert not (tmp_path / "escape.json").exists()


def test_req_exp_1_3_the_shard_index_is_deterministic():
    """The index lists neighborhoods, years and counts only, so a rerun is byte-identical."""
    result, cases, ctx = town_inputs()
    a, b = build_payloads(result, cases, ctx), build_payloads(result, cases, ctx)
    assert a["zombies/index.json"] == b["zombies/index.json"]


def test_req_ing_dept_3_a_test_department_case_is_excluded_and_counted():
    """Owner decision 2026-11-16: department Test is test data, dropped by `clean` and counted under `test_data`."""
    from undead311.ingest.clean import clean, ids_by_reason

    con = duckdb.connect()
    con.execute("create table cases_x(id varchar, system varchar, type_family varchar, type_raw varchar, scope_tier varchar, "
                "lat double, lon double, open_time_utc timestamp, department varchar)")
    con.executemany("insert into cases_x values (?,?,?,?,?,?,?,try_cast(? as timestamp),?)", [
        ("a", "legacy", "pothole_roadway", "x", "core", 42.3, -71.1, "2024-01-01 00:00:00", "PWDx"),
        ("t", "legacy", "pothole_roadway", "x", "core", 42.3, -71.1, "2024-01-01 00:00:00", "Test"),
    ])  # fmt: skip
    report = clean(con)
    assert report.counts["test_data"] == 1 and ids_by_reason(con)["test_data"] == ["t"]
    assert [r[0] for r in con.execute("select id from cases_clean").fetchall()] == ["a"]


# ---- REQ-STAT-AREA: each original's p comes from its own match area (methods.md, 2026-11-16) -------------------------------


def test_req_stat_area_1_the_match_area_is_the_detectors_rule():
    """Same segment within MAX_SEGMENT_DIST, RADIUS_M when unsnapped; a report 300 m along the same segment is not in the area."""
    from undead311.stats.areas import MatchAreas

    cs = [mk("A", 0, 1, segment="S"), mk("near", 50, x=40.0, segment="S"), mk("far", 60, x=300.0, segment="S"),
          mk("loose", 70, x=20.0, segment=None, snap=None), mk("loose_far", 80, x=45.0, segment=None, snap=None),
          mk("other_seg", 90, x=10.0, segment="T")]  # fmt: skip
    by = {c.id: c for c in cs}
    res = detect(cs)
    inc = next(i for i in res.incidents if "A" in i.member_ids)
    areas = MatchAreas(by, res.incidents, res.mirror_ids)
    assert set(areas.ids(areas.of_incident[inc.incident_id])) == {"A", "near", "loose"}


def test_req_stat_area_1_reports_outside_the_match_area_never_change_p():
    """Adding busy reports 300 m along the same segment (outside every match) leaves the original's p as it was."""
    base = [mk("A", 0, 1, segment="S")] + [mk(f"R{i}", 150 + 150 * i, segment="S", x=10.0) for i in range(6)]
    extra = [mk(f"F{i}", 30 + 20 * i, segment="S", x=300.0) for i in range(40)]
    ps = []
    for cs in (base, base + extra):
        by = {c.id: c for c in cs}
        res = detect(cs)
        m = BaselineModel(by, res, data_end=day(1500))
        inc = next(i for i in res.incidents if "A" in i.member_ids)
        ps.append(m.p(inc))
    assert ps[0] is not None and ps[0] == pytest.approx(ps[1])


def test_req_stat_pop_4_source_unknown_counts_only_originals_whose_window_reaches_the_new_system():
    """Owner decision 2026-11-16: a new-system re-report needs the new system; an original whose window ends before the first
    new-system case is not in the source_unknown cohort."""
    cs = [mk("old", 0, 1, label="made_safe_temporary"), mk("late", 400, 401, x=500, label="made_safe_temporary"),
          mk("N1", 420, system="new", x=900)]  # fmt: skip
    by = {c.id: c for c in cs}
    res = detect(cs)
    su = next(t for t in tier_models(by, res, data_end=day(900)) if t.tier == "source_unknown")
    members = {m for i in su.model.incidents for m in i.member_ids}
    assert "late" in members and "old" not in members
    head = next(t for t in tier_models(by, res, data_end=day(900)) if t.tag == "headline-after-planned-label")
    assert {m for i in head.model.incidents for m in i.member_ids} >= {"old", "late"}  # the headline cohort is unchanged


def test_req_stat_sf_4_no_export_carries_the_adjusted_stayed_fixed_rate(tmp_path):
    """Owner decision 2026-11-17: `stayed_fixed_adj` is null in every scorecard the stats stage writes, with and without city re-reports."""
    from undead311.stats.pipeline import EXPORT_ADJUSTED_RATE

    assert EXPORT_ADJUSTED_RATE is False
    out = tmp_path / "out"
    run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "data", grid=False, run_time="2026-11-17T00:00:00Z")
    sc = json.loads((out / "stats" / "scorecard.json").read_text())
    cards = sc["scorecards"] + sc["without_city_originated"]["scorecards"]
    assert cards and all(c["stayed_fixed_adj"] is None for c in cards)
    assert all(c["stayed_fixed_raw"]["rate"] is None or c["stayed_fixed_raw"]["rate"] <= c["on_time"]["rate"] for c in cards)
