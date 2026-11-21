"""The run's exports in the judging section, the committed judge-mode files, and `make judging-final` (REQ-OPS-SNAP.3, .4).

A fake full run lives in `$DATA_DIR/exports/<run>` (zombie shards, points, cards, stats) with a processed folder beside it. The
tests drive `snapshot.py --run-id` and `judging_final.py` in-process and check what changed, what must not, and what a plain
checkout can verify afterwards.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from undead311 import snapshot as snap
from undead311.export.writers import canonical_json, validate
from undead311.stats import records_check as rc
from undead311.stats import validation as val
from undead311.stats.tour import JudgeTour

REPO = Path(__file__).resolve().parents[3]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "pipeline" / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


snapshot_cli, judging_final = load("snapshot"), load("judging_final")
RUN, VERSION = "full-9", "2026-11-20+abc1234+0123abcd"
PARAMS = {"RADIUS_M": 30, "WINDOW_DAYS": 60, "matching": "segment"}
HOODS = ["Roxbury", "South End", "Mission Hill"]


def zombie(i: int) -> dict:
    return {"zombie_id": f"z{i:02d}", "tier": "headline", "skeptic_verdict": "survives", "gap_days": 10.0 + i,
            "city_rereport": False, "reports_after": 1 + i % 3, "neighborhood": HOODS[i % 3], "resurrection_date": "2026-11-10"}  # fmt: skip


def write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode())


@pytest.fixture
def world(tmp_path, monkeypatch):
    """data/ (snapshot, labels, docs) and a fake full run, provisionally snapshotted."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data_dir"))
    base = tmp_path / "data_dir"
    exp, proc = base / "exports" / RUN, base / "processed"
    zs = [zombie(i) for i in range(8)]
    shard_rows: dict[str, list[dict]] = {}
    for z in zs:
        shard_rows.setdefault(f"{snap.slug(z['neighborhood'])}-2026", []).append(z)
    for shard, rows in shard_rows.items():
        write(exp / "zombies" / f"{shard}.json", canonical_json({"data_version": VERSION, "shard": shard, "zombies": rows}))
        write(exp / "cards" / f"{shard}.json", canonical_json({"cards": [r["zombie_id"] for r in rows]}))
    write(exp / "zombies" / "index.json", "{}")
    write(exp / "points.json", canonical_json({"id": [z["zombie_id"] for z in zs], "neighborhood": [z["neighborhood"] for z in zs], "year": [2026] * 8}))
    write(exp / "status.json", canonical_json({"ok": True, "dataset": "full", "data_version": VERSION, "data_end": "2026-11-19", "anomalies": []}))
    sample = [z["zombie_id"] for z in zs]
    prov = JudgeTour(True, ("z00", "z01", "z02"), "most_reports").to_json(VERSION, dataset="full")
    awaiting = {**val.score(sample, {}).to_json(VERSION), "dataset": "full", "params": PARAMS, "seed": None}
    validate("validation", awaiting)
    validate("judge_tour", prov)
    write(exp / "stats" / "judge_tour.json", canonical_json({**prov, "params": PARAMS}))
    write(exp / "stats" / "validation.json", canonical_json(awaiting))
    write(exp / "stats" / "scorecard.json", "{}")
    write(proc / "run_report.json", canonical_json({"data_version": VERSION}))
    write(base / "raw" / "311_2026.csv", b"id\n1\n")
    labels = tmp_path / "labels"
    labels.mkdir()
    with (labels / "validation_sample.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(val.SAMPLE_COLUMNS)
        for zid in sample:
            w.writerow([zid, "", "", "", "", ""])
    snapshot = tmp_path / "repo" / "data" / "SNAPSHOT.md"
    write(snapshot, "# Data snapshot\n\nDownloaded: 2026-11-18\n\n| file | resource | last_modified | bytes | sha256 |\n|---|---|---|---|---|\n")
    assert snapshot_cli.main(["--run-id", RUN, "--snapshot", str(snapshot)]) == 0
    return {"tmp": tmp_path, "exp": exp, "proc": proc, "labels": labels, "snapshot": snapshot, "judging": snapshot.parent / "judging",
            "md": tmp_path / "repo" / "docs" / "VALIDATION.md", "sample": sample}  # fmt: skip


def label(world, confirmed: int, pairs: int | None = None) -> None:
    rows = []
    for i, zid in enumerate(world["sample"][: pairs if pairs is not None else confirmed]):
        lab = "still broken" if i < confirmed else "fixed since"
        rows += [(zid, "a", lab), (zid, "b", lab)]
    with (world["labels"] / "validation_labels.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["zombie_id", "rater", "label"])
        w.writerows(rows)


def final(world, *extra) -> int:
    return judging_final.main(["--run-id", RUN, "--labels-dir", str(world["labels"]), "--validation-md", str(world["md"]),
                               "--snapshot", str(world["snapshot"]), *extra])  # fmt: skip


def tree(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


# ---- make snapshot RUN_ID (REQ-OPS-SNAP.3) -------------------------------------------------------------------------------------

def test_req_ops_snap_3_the_section_names_the_run_the_stage_and_hashes_the_runs_own_exports(world):
    text = world["snapshot"].read_text()
    assert f"Run: `{RUN}`, data version `{VERSION}`." in text and "Stage: provisional" in text
    assert "`judged-2026-11-19`" in text and "web/public/data/stats/judge_tour.json" in text and "raw/311_2026.csv" in text
    assert text.index("Downloaded: 2026-11-18") < text.index(snap.BEGIN)  # the download table above is untouched


def test_req_ops_snap_3_the_tag_carries_exactly_the_judge_mode_files_and_a_plain_checkout_can_verify_it(world):
    """The chosen design: the judging table is the manifest of every export; data/judging/ holds the files judge mode reads."""
    j = tree(world["judging"])
    tour = json.loads((world["exp"] / "stats" / "judge_tour.json").read_text())["zombie_ids"]
    assert sorted(j) == sorted({"points.json", "stats/judge_tour.json", *[f"cards/{snap.slug(HOODS[int(z[1:]) % 3])}-2026.json" for z in tour]})
    assert snap.check_committed(world["snapshot"].read_text(), world["judging"]) == []
    assert snapshot_cli.main(["--verify", "--snapshot", str(world["snapshot"])]) == 0


@pytest.mark.parametrize("damage", ["file", "extra", "missing_folder", "hand_edited_table", "row_removed"])
def test_req_ops_snap_3_verify_fails_on_any_damage_to_the_tag(world, damage, capsys):
    text = world["snapshot"].read_text()
    if damage == "file":
        write(world["judging"] / "points.json", "{}")
    elif damage == "extra":
        write(world["judging"] / "cards" / "stray.json", "{}")
    elif damage == "missing_folder":
        for p in sorted(world["judging"].rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    elif damage == "hand_edited_table":
        digest = next(r[2] for r in snap.section_rows(text) if r[0].endswith("scorecard.json"))
        world["snapshot"].write_text(text.replace(digest, "0" * 64))
    else:
        row = next(line for line in text.splitlines() if "stats/judge_tour.json" in line and line.startswith("|"))
        world["snapshot"].write_text(text.replace(row + "\n", ""))
    assert snapshot_cli.main(["--verify", "--snapshot", str(world["snapshot"])]) == 1
    assert "NOT consistent" in capsys.readouterr().out


def test_req_ops_snap_3_nightly_freezes_judge_mode_from_the_tag_not_from_web_public_data(world, tmp_path):
    """A checkout whose web/public/data holds another export (the sample) still freezes the snapshot's files."""
    public = tmp_path / "checkout" / "web" / "public" / "data"
    write(public / "points.json", "{}")  # unrelated sample data
    copied = snap.freeze_judge(public, world["snapshot"].read_text(), world["judging"])
    assert "points.json" in copied and (public / "frozen" / "points.json").read_bytes() == (world["exp"] / "points.json").read_bytes()
    assert snap.check_frozen(public, world["snapshot"].read_text()) == []


def test_req_ops_snap_3_the_check_reads_the_recorded_run_and_stage_and_a_changed_export_fails_it(world):
    args = ["--check", "--run-id", RUN, "--snapshot", str(world["snapshot"])]
    assert snapshot_cli.main(args) == 0
    write(world["exp"] / "stats" / "scorecard.json", '{"changed": true}')
    assert snapshot_cli.main(args) == 1


def test_req_ops_snap_3_make_snapshot_never_writes_into_web_public_data(world):
    status = (REPO / "web" / "public" / "data" / "status.json").read_bytes()
    assert snapshot_cli.main(["--run-id", RUN, "--snapshot", str(world["snapshot"])]) == 0
    assert (REPO / "web" / "public" / "data" / "status.json").read_bytes() == status
    assert not (REPO / "web" / "public" / "data" / "frozen").exists()


@pytest.mark.parametrize("what", ["failed", "dry_run", "sample", "other_run_processed"])
def test_req_ops_snap_3_a_failed_dry_sample_or_foreign_run_is_not_snapshotted(world, what):
    st = json.loads((world["exp"] / "status.json").read_text())
    if what == "failed":
        st["ok"] = False
    elif what == "dry_run":
        st["anomalies"] = ["DRY RUN ONLY, over the first-view budget"]
    elif what == "sample":
        st["dataset"] = "sample"
    else:
        write(world["proc"] / "run_report.json", canonical_json({"data_version": "2026-11-12+old+old"}))
    write(world["exp"] / "status.json", canonical_json(st))
    before = world["snapshot"].read_text()
    with pytest.raises(SystemExit, match="snapshot:"):
        snapshot_cli.main(["--run-id", RUN, "--snapshot", str(world["snapshot"])])
    assert world["snapshot"].read_text() == before


def test_req_ops_snap_3_make_snapshot_needs_a_run_id():
    mk = (REPO / "Makefile").read_text()
    assert 'make snapshot RUN_ID=' in mk and "snapshot.py --run-id $(RUN_ID)" in mk and "snapshot.py --verify" in mk


# ---- make judging-final (REQ-OPS-SNAP.4) ----------------------------------------------------------------------------------------

def test_req_ops_snap_4_while_no_labels_exist_it_changes_nothing_and_the_tour_stays_provisional(world):
    before = (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match="awaiting field labels"):
        final(world)
    assert (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"])) == before
    assert json.loads((world["exp"] / "stats" / "validation.json").read_text())["status"] == "awaiting_field_labels"
    assert json.loads((world["exp"] / "stats" / "judge_tour.json").read_text())["provisional"] is True


def test_req_ops_snap_4_fewer_than_three_confirmed_zombies_changes_nothing(world):
    label(world, confirmed=2, pairs=5)
    before = (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match="needs at least 3"):
        final(world)
    assert (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"])) == before


def test_req_ops_snap_4_with_labels_only_the_validation_and_tour_files_change_and_the_final_tag_verifies(world):
    label(world, confirmed=4, pairs=6)
    exp_before, old = tree(world["exp"]), world["snapshot"].read_text()
    assert final(world) == 0
    exp_after, new = tree(world["exp"]), world["snapshot"].read_text()
    assert {k for k in exp_after if exp_after[k] != exp_before[k]} == {"stats/validation.json", "stats/judge_tour.json"}
    v, t = (json.loads((world["exp"] / "stats" / f).read_text()) for f in ("validation.json", "judge_tour.json"))
    assert v["status"] == "scored" and v["n_paired"] == 6 and len(v["confirmed"]) == 4 and v["dataset"] == "full" and v["params"] == PARAMS
    assert t["provisional"] is False and set(t["zombie_ids"]) <= set(v["confirmed"]) and t["data_version"] == VERSION and t["params"] == PARAMS
    assert "Stage: final" in new and "`judged-2026-11-19-final`" in new and f"Run: `{RUN}`" in new
    changed = snap.row_changes(snap.section_rows(old), snap.section_rows(new))
    assert set(changed) == {"web/public/data/stats/validation.json", "web/public/data/stats/judge_tour.json"}
    assert new[: new.index(snap.BEGIN)] == old[: old.index(snap.BEGIN)]
    assert "Precision" in world["md"].read_text()
    assert snap.check_committed(new, world["judging"]) == []
    assert snapshot_cli.main(["--check", "--run-id", RUN, "--snapshot", str(world["snapshot"])]) == 0
    assert tree(world["judging"])["stats/judge_tour.json"] == exp_after["stats/judge_tour.json"]  # judge mode gets the final tour
    assert final(world) == 0 and world["snapshot"].read_text() == new  # a rerun with the same labels changes nothing


def test_req_ops_snap_4_the_owners_override_is_used_when_it_names_three_confirmed_zombies(world):
    label(world, confirmed=5)
    write(world["labels"] / "judge_tour_override.json", json.dumps({"zombie_ids": ["z04", "z03", "z01"]}))
    assert final(world) == 0
    assert json.loads((world["exp"] / "stats" / "judge_tour.json").read_text())["zombie_ids"] == ["z04", "z03", "z01"]


def test_req_ops_snap_4_other_export_changes_stop_it_and_put_the_two_files_back(world):
    label(world, confirmed=4)
    write(world["exp"] / "stats" / "scorecard.json", '{"drifted": true}')
    before = (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match=r"scorecard\.json \(changed\)"):
        final(world)
    assert (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"])) == before


def test_req_ops_snap_4_a_dry_run_writes_nothing(world, capsys):
    label(world, confirmed=4)
    before = (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"]))
    assert final(world, "--dry-run") == 0
    assert (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"])) == before
    assert "dry run" in capsys.readouterr().out and not world["md"].exists()


def test_req_ops_snap_4_it_refuses_a_run_the_section_does_not_name(world):
    with pytest.raises(SystemExit, match="no judging section for run other-run"):
        judging_final.main(["--run-id", "other-run", "--labels-dir", str(world["labels"]), "--snapshot", str(world["snapshot"])])


def test_req_ops_snap_4_make_judging_final_is_wired():
    mk = (REPO / "Makefile").read_text()
    assert "judging-final:" in mk and "pipeline/scripts/judging_final.py --run-id $(RUN_ID)" in mk


def test_req_ops_snap_4_the_provisional_tour_works_while_validation_says_awaiting_field_labels():
    """Friday's snapshot: no labels, so the tour is the provisional ranking and still has three zombies."""
    from types import SimpleNamespace

    from undead311.stats.tour import build_tour

    zs = [SimpleNamespace(zombie_id=f"z{i}", tier="headline", skeptic_verdict="survives", gap_days=5.0, city_rereport=False, reports_after=i)
          for i in range(6)]  # fmt: skip
    v = val.score([z.zombie_id for z in zs], {})
    assert v.status == "awaiting_field_labels" and v.confirmed == ()
    tour = build_tour(zs, None, v.confirmed)
    assert tour is not None and tour.provisional is True and len(tour.zombie_ids) == 3
    validate("judge_tour", tour.to_json(VERSION, dataset="full"))


# ---- make judging-final from the records check (REQ-STAT-VAL.5, owner decision 2026-11-21: no field visits) ------------------------

def records(world, repaired: int, ambiguous: int = 0) -> None:
    """validation_records.csv for the sample: the first `repaired` are repaired again (the next `ambiguous` of them ambiguous)."""
    rows = []
    for i, zid in enumerate(world["sample"]):
        sure = i < repaired
        amb = repaired <= i < repaired + ambiguous
        rows.append({"zombie_id": zid, "resurrection_id": f"r{i}", "type_family": "pothole_roadway", "neighborhood": HOODS[i % 3],
                     "system": "new", "status": "Closed", "status_at_snapshot": "Closed", "closure_code": "Resolved",
                     "coroner_label": "resolved" if sure or amb else "noted", "label_source": "table", "closure_text": "",
                     "class": "repaired_again" if sure or amb else "invalid_or_nothing_found",
                     "ambiguous_reason": "conflicting_cue" if amb else "", "checked_on": "2026-11-21"})  # fmt: skip
    rc.write_records(world["labels"] / rc.RECORDS_FILE, rows)


def test_req_stat_val_5_records_confirm_the_tour_and_it_says_record_confirmed(world):
    records(world, repaired=5, ambiguous=1)
    assert final(world) == 0
    tour = json.loads((world["exp"] / "stats" / "judge_tour.json").read_text())
    v = json.loads((world["exp"] / "stats" / "validation.json").read_text())
    assert tour["provisional"] is False and tour["confirmation"] == "records"
    assert set(tour["zombie_ids"]) <= set(v["confirmed"]) and len(v["confirmed"]) == 5  # the ambiguous one is not confirmed
    assert v["method"] == "records" and v["precision"]["k"] == 5 and v["precision"]["n"] == 8
    assert v["records"]["ambiguous_ids"] == [world["sample"][5]] and v["records"]["checked_on"] == "2026-11-21"
    md = world["md"].read_text()
    assert "Records-based check" in md and "No field visits were made" in md and "not what is on the street" in md


def test_req_stat_val_5_fewer_than_three_record_confirmed_changes_nothing(world):
    records(world, repaired=2, ambiguous=3)
    before = (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match="repaired again in the records"):
        final(world)
    assert (tree(world["exp"]), world["snapshot"].read_text(), tree(world["judging"])) == before


def test_req_stat_val_5_field_labels_win_in_auto_and_records_are_used_only_when_asked_or_alone(world):
    records(world, repaired=5)
    label(world, confirmed=4)
    assert final(world) == 0
    assert json.loads((world["exp"] / "stats" / "judge_tour.json").read_text())["confirmation"] == "field"


def test_req_stat_val_5_the_records_source_ignores_field_labels(world):
    records(world, repaired=5)
    label(world, confirmed=4)
    assert final(world, "--source", "records") == 0
    assert json.loads((world["exp"] / "stats" / "judge_tour.json").read_text())["confirmation"] == "records"


def test_req_stat_val_5_a_records_tour_skips_a_re_report_opened_within_an_hour_of_the_closure(world):
    """No one is on the street, so the ops#44 rule (a crew's work log is not a resurrection to show) still applies."""
    records(world, repaired=4)
    for shard in (world["exp"] / "zombies").glob("*.json"):
        if shard.name == "index.json":
            continue
        d = json.loads(shard.read_text())
        for z in d["zombies"]:
            if z["zombie_id"] in world["sample"][:3]:
                z["gap_days"] = 0.01  # 14 minutes
        write(shard, canonical_json(d))
    with pytest.raises(SystemExit, match="repaired again in the records"):
        final(world)
