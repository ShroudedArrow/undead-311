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


# ---- make judging-final ARCHIVE_SHA256=... (exports-only, REQ-OPS-SNAP.5) ---------------------------------------------------------
# The download itself is tested against a mock GitHub in test_exports_release_rest.py; here `fetch_release` is replaced by a stand-in
# that unpacks a locally packed copy of the run's exports, with the same hash check, so the judging logic runs on the real files.

def release(world, monkeypatch, tmp_path_factory=None, mutate=None) -> str:
    """Pack the run's provisional exports as the release, then drop raw/ and processed/ and the export folder: this machine has none."""
    rel = world["tmp"] / "release"
    if mutate:
        mutate(world["exp"])
    archive, _ = judging_final.er.pack(RUN, world["exp"], rel)
    want = judging_final.er.sha256_file(archive)

    def fake(run_id, dest, expected, repo=None, token=None, api_url=None, transport="rest"):
        if judging_final.er.sha256_file(archive) != expected:
            raise judging_final.er.ExportsError(f"SHA-256 mismatch for {archive.name}: the snapshot recorded {expected[:12]}")
        return judging_final.er.unpack(archive, rel / f"exports-{run_id}.sha256", dest / "exports")

    monkeypatch.setattr(judging_final.er, "fetch_release", fake)
    return want


def only(world, sha: str, *extra) -> int:
    return final(world, "--source", "records", "--exports-only", "--archive-sha256", sha, *extra)


def strip_machine(world) -> None:
    import shutil

    for p in (world["proc"], world["tmp"] / "data_dir" / "raw", world["tmp"] / "data_dir" / "exports"):
        shutil.rmtree(p)


def test_req_ops_snap_5_exports_only_changes_the_two_files_carries_raw_and_processed_and_says_so(world, monkeypatch):
    records(world, repaired=5)
    old = world["snapshot"].read_text()
    sha = release(world, monkeypatch)
    exp_before = tree(world["exp"])
    strip_machine(world)
    assert only(world, sha) == 0
    new = world["snapshot"].read_text()
    changed = snap.row_changes(snap.section_rows(old), snap.section_rows(new))
    assert set(changed) == {"web/public/data/stats/validation.json", "web/public/data/stats/judge_tour.json"}
    carried = lambda t: [r for r in snap.section_rows(t) if not r[0].startswith(snap.PUBLIC_PREFIX)]
    assert carried(new) == carried(old) and any(r[0] == "raw/311_2026.csv" for r in carried(new))
    assert snap.section_counts(new) == snap.section_counts(old)
    assert f"{snap.NOTE_PREFIX}exports checked against release `exports-{RUN}` (archive sha256 `{sha}`)" in new
    assert "not re-hashed here" in new and "Stage: final" in new and "`judged-2026-11-19-final`" in new
    assert snap.check_committed(new, world["judging"]) == [] and snapshot_cli.main(["--verify", "--snapshot", str(world["snapshot"])]) == 0
    tour = json.loads((world["judging"] / "stats" / "judge_tour.json").read_text())
    assert tour["provisional"] is False and tour["confirmation"] == "records" and set(exp_before) >= {"stats/judge_tour.json"}
    assert "Records-based check" in world["md"].read_text()
    assert not list((world["tmp"] / "data_dir").glob("exports-only-*"))  # the scratch folder is gone
    # the release still holds the provisional files, so a rerun refuses until the final exports are published again
    with pytest.raises(SystemExit, match=r"stats/judge_tour\.json \(changed\)"):
        only(world, sha)
    assert world["snapshot"].read_text() == new


def test_req_ops_snap_5_exports_only_writes_the_same_table_as_the_full_mode(world, monkeypatch):
    """The two modes differ in the note only: the rows, the combined hash, the judge-mode files and VALIDATION.md are equal."""
    records(world, repaired=5)
    old = world["snapshot"].read_text()
    sha = release(world, monkeypatch)
    assert only(world, sha) == 0
    text_only, judged_only, md_only = world["snapshot"].read_text(), tree(world["judging"]), world["md"].read_text()
    world["snapshot"].write_text(old)
    world["md"].unlink()
    assert final(world, "--source", "records") == 0
    assert snap.NOTE_PREFIX not in world["snapshot"].read_text()
    assert snap.strip_note(text_only) == world["snapshot"].read_text()
    assert judged_only == tree(world["judging"]) and md_only == world["md"].read_text()


def test_req_ops_snap_5_the_full_data_check_ignores_the_note(world, monkeypatch):
    records(world, repaired=5)
    sha = release(world, monkeypatch)
    assert only(world, sha) == 0
    with_note = world["snapshot"].read_text()
    assert snap.NOTE_PREFIX in with_note
    assert final(world, "--source", "records") == 0  # writes the final export files here, and a section without the note
    world["snapshot"].write_text(with_note)
    assert snapshot_cli.main(["--check", "--run-id", RUN, "--snapshot", str(world["snapshot"])]) == 0


def test_req_ops_snap_5_a_wrong_recorded_hash_changes_nothing(world, monkeypatch):
    records(world, repaired=5)
    release(world, monkeypatch)
    before = (world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match="SHA-256 mismatch.*Nothing changed"):
        only(world, "0" * 64)
    assert (world["snapshot"].read_text(), tree(world["judging"])) == before and not world["md"].exists()


@pytest.mark.parametrize("drift", ["changed", "added", "removed"])
def test_req_ops_snap_5_a_release_that_differs_from_the_section_changes_nothing(world, monkeypatch, drift):
    records(world, repaired=5)

    def mutate(exp):
        if drift == "changed":
            write(exp / "stats" / "scorecard.json", '{"drifted": true}')
        elif drift == "added":
            write(exp / "cards" / "stray-2026.json", "{}")
        else:
            (exp / "cards" / "roxbury-2026.json").unlink()

    sha = release(world, monkeypatch, mutate=mutate)
    before = (world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match=rf"does not match the judging section.*\({drift}\).*Nothing changed"):
        only(world, sha)
    assert (world["snapshot"].read_text(), tree(world["judging"])) == before and not world["md"].exists()


def test_req_ops_snap_5_a_release_of_another_data_version_is_refused(world, monkeypatch):
    records(world, repaired=5)

    def mutate(exp):
        st = json.loads((exp / "status.json").read_text())
        write(exp / "status.json", canonical_json({**st, "data_version": "2026-11-20+other+other"}))

    sha = release(world, monkeypatch, mutate=mutate)
    with pytest.raises(SystemExit, match="data_version 2026-11-20\\+other\\+other differs"):
        only(world, sha)


def test_req_ops_snap_5_a_hand_edited_section_is_refused(world, monkeypatch):
    records(world, repaired=5)
    sha = release(world, monkeypatch)
    text = world["snapshot"].read_text()
    digest = next(r[2] for r in snap.section_rows(text) if r[0].startswith("raw/"))
    world["snapshot"].write_text(text.replace(digest, "0" * 64))  # the carried rows would be taken on trust
    with pytest.raises(SystemExit, match="not self-consistent"):
        only(world, sha)


def test_req_ops_snap_5_anything_besides_the_two_files_changing_stops_it_and_writes_nothing(world, monkeypatch):
    """Even when the release matches the section, a plan that also touched another export file is refused."""
    records(world, repaired=5)
    sha = release(world, monkeypatch)
    real_plan = judging_final.plan

    def greedy(public, labels_dir, source="auto"):
        out = real_plan(public, labels_dir, source)
        write(public / "stats" / "scorecard.json", '{"touched": true}')
        return out

    monkeypatch.setattr(judging_final, "plan", greedy)
    before = (world["snapshot"].read_text(), tree(world["judging"]))
    with pytest.raises(SystemExit, match=r"scorecard\.json \(changed\)\. Nothing was written"):
        only(world, sha)
    assert (world["snapshot"].read_text(), tree(world["judging"])) == before and not world["md"].exists()


def test_req_ops_snap_5_a_dry_run_writes_nothing(world, monkeypatch, capsys):
    records(world, repaired=5)
    sha = release(world, monkeypatch)
    before = (world["snapshot"].read_text(), tree(world["judging"]))
    assert only(world, sha, "--dry-run") == 0
    assert (world["snapshot"].read_text(), tree(world["judging"])) == before and not world["md"].exists()
    assert "dry run" in capsys.readouterr().out


@pytest.mark.parametrize("args,msg", [
    (["--exports-only"], "needs --archive-sha256"),
    (["--archive-sha256", "a" * 64], "only for --exports-only"),
    (["--exports-only", "--archive-sha256", "a" * 64, "--raw", "x"], "takes no --public, --processed or --raw"),
])
def test_req_ops_snap_5_the_flags_are_checked(world, args, msg):
    with pytest.raises(SystemExit, match=msg):
        final(world, *args)


def test_req_ops_snap_5_the_makefile_turns_archive_sha256_into_exports_only():
    mk = (REPO / "Makefile").read_text()
    assert "--exports-only --archive-sha256 $(ARCHIVE_SHA256)" in mk and "--transport $(TRANSPORT)" in mk
