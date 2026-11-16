"""REQ-ING-1, REQ-ING-NIGHTLY.1-2, REQ-ING-SAMPLE.1: orchestration end to end on a tiny raw folder and on the sample."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from undead311.ingest.load import RawFileMissing
from undead311.pipeline import run_pipeline

LEGACY_HEAD = ("case_enquiry_id,open_dt,closed_dt,case_status,closure_reason,type,department,neighborhood,"
               "location_street_name,latitude,longitude,source\n")  # fmt: skip
NEW_HEAD = ("case_id,longitude,latitude,open_date,close_date,case_status,closure_reason,closure_comments,service_name,"
            "assigned_department,neighborhood,street_name,report_source\n")  # fmt: skip


def raw_folder(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "311_2024.csv").write_text(
        LEGACY_HEAD
        + "1001,2024-03-04 09:12:00,2024-03-05 10:00:00,Closed,Case Closed Resolved,Request for Pothole Repair,PWDx,Dorchester,Test St,42.27,-71.14,Constituent Call\n"
        + "1002,2024-03-20 09:00:00,,Open,,Request for Pothole Repair,PWDx,Dorchester,Test St,42.27,-71.14,Citizens Connect App\n"
        + "1003,2024-03-20 09:00:00,,Open,,Graffiti Removal,PWDx,Dorchester,Test St,42.27,-71.14,Citizens Connect App\n"
        + "1004,2024-03-20 09:00:00,,Open,,Request for Pothole Repair,PWDx,Dorchester,Test St,42.3603,-71.0583,Citizens Connect App\n"
    )
    (raw / "311_new_system.csv").write_text(
        NEW_HEAD + "BCS-00000001,-71.14,42.27,2025-09-01 09:00:00+00,,In progress,,,Pothole,PWD,Dorchester,Test St,BOS311\n"
    )
    snap = tmp_path / "SNAPSHOT.md"
    snap.write_text("Downloaded: 2026-11-12\n\n| file |\n|---|\n| 311_2024.csv |\n| 311_new_system.csv |\n")
    return raw, snap


def test_req_ing_1_full_pipeline_on_a_tiny_raw_folder(tmp_path):
    """REQ-ING-1.1, REQ-ING-NIGHTLY.1: raw CSVs -> DuckDB -> detect -> validated exports and a run report."""
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert rep.ok and rep.row_counts["raw_legacy"] == 4 and rep.row_counts["raw_new"] == 1
    assert rep.exclusions["excluded_type"] == 1 and rep.exclusions["placeholder"] == 1
    assert rep.tier_counts == {"headline": 1, "source_unknown": 0, "city_rereport": 0, "sensitivity": 0}
    zs = json.loads((out / "zombies.json").read_text())["zombies"]
    assert [z["zombie_id"] for z in zs] == ["1001:1002"]
    status = json.loads((out / "status.json").read_text())
    assert status["headline_count"] == 1 and status["data_version"].startswith("2026-11-12+")
    ex = json.loads((out / "exclusions.json").read_text())
    assert ex["excluded_ids"]["placeholder"] == ["1004"] and ex["excluded_ids"]["excluded_type"] == ["1003"]
    db = tmp_path / "data" / "processed" / "undead311.duckdb"
    assert duckdb.connect(str(db), read_only=True).execute("select zombie_id from zombies").fetchall() == [("1001:1002",)]
    assert (tmp_path / "data" / "processed" / "skeptic_input.json").is_file()
    assert (tmp_path / "data" / "processed" / "coroner_templates.csv").is_file()
    assert json.loads((tmp_path / "data" / "processed" / "run_report.json").read_text())["label_coverage"] <= 1


def test_req_ing_1_2_missing_raw_file_stops_the_run_and_leaves_no_outputs(tmp_path):
    """REQ-ING-1.2, REQ-ING-NIGHTLY.1: a missing file names the download command; nothing is exported or renamed."""
    raw, snap = raw_folder(tmp_path)
    snap.write_text(snap.read_text() + "| 311_2025.csv |\n")
    with pytest.raises(RawFileMissing, match="make data-download"):
        run_pipeline(out_dir=tmp_path / "out", raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap)
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "data" / "processed" / "undead311.duckdb").exists()


def test_req_ing_sample_1_sample_run_needs_no_raw_data_and_writes_valid_files(tmp_path):
    """REQ-ING-NIGHTLY.2, REQ-ING-SAMPLE.1: `pipeline --sample` runs on data/sample into processed-sample."""
    out = tmp_path / "out"
    rep = run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "data", run_time="2026-11-13T00:00:00Z")
    assert rep.ok and rep.row_counts["sample_rows"] > 10_000 and rep.tier_counts["headline"] > 0
    assert (tmp_path / "data" / "processed-sample" / "undead311.duckdb").is_file()
    assert (out / "status.json").is_file() and (out / "zombies.json").is_file()
    assert rep.excluded_pairs["transferred_original"] > 0 and rep.file_sizes["status.json"] > 0
    assert "sample" in rep.summary()
    # ops#29, REQ-DET-TIER.3: city re-reports are their own tier; the share and the under-1-h count are reported, with the
    # planned follow-ups kept out
    co = rep.city_origin
    assert co["headline"] == rep.tier_counts["headline"] and co["city_rereport"] == rep.tier_counts["city_rereport"] > 0
    assert co["city_rereport_under_1h"] <= co["city_rereport"]
    assert "city re-reports (outside the headline)" in rep.summary()
    status = json.loads((out / "status.json").read_text())
    assert status["city_rereport_count"] == co["city_rereport"]
    assert status["city_rereport_under_1h_count"] == co["city_rereport_under_1h"]
    assert "headline_city_originated_count" not in status
    assert status["mirror_copies_merged"] == rep.mirror_copies_merged  # ops#46
    assert status["planned_followup_count"] == rep.planned_followups
    if co["city_rereport_share"] >= 0.5:
        assert any("city re-reports" in a for a in status["anomalies"])


def test_req_stat_exp_1_stats_ran_and_a_stale_tour_is_removed(tmp_path):
    """REQ-STAT-EXP.1: the stats stage runs, writes scorecard.json, and removes a judge_tour.json it did not produce."""
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    (out / "stats").mkdir(parents=True)
    stale = out / "stats" / "judge_tour.json"
    stale.write_text('{"zombie_ids": ["old:1", "old:2", "old:3"]}')
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert rep.stats == "ran"
    assert (out / "stats" / "scorecard.json").is_file() and (out / "stats" / "stats_status.json").is_file()
    assert not stale.exists()  # one headline zombie only: no tour this run
    assert "calibration_warning" in json.loads((out / "status.json").read_text())


def test_req_stat_exp_1_a_dependency_missing_inside_stats_fails_the_run(tmp_path, monkeypatch):
    """REQ-STAT-EXP.1: only an absent stats package is "not present"; a missing dependency inside it is an error."""
    import importlib

    real = importlib.import_module

    def fake(name, *a, **k):
        if name == "undead311.stats.pipeline":
            raise ModuleNotFoundError("No module named 'lifelines'", name="lifelines")
        return real(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", fake)
    raw, snap = raw_folder(tmp_path)
    with pytest.raises(ModuleNotFoundError, match="lifelines"):
        run_pipeline(out_dir=tmp_path / "out", raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap)


def test_req_stat_exp_1_an_absent_stats_package_is_not_present(tmp_path, monkeypatch):
    """REQ-STAT-EXP.1: with no stats package the run goes on, and an old stats_status.json is not folded into status.json."""
    import importlib

    real = importlib.import_module

    def fake(name, *a, **k):
        if name == "undead311.stats.pipeline":
            raise ModuleNotFoundError("No module named 'undead311.stats'", name="undead311.stats")
        return real(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", fake)
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    (out / "stats").mkdir(parents=True)
    (out / "stats" / "stats_status.json").write_text('{"calibration_warning": "stale"}')
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert rep.stats == "not present"
    assert json.loads((out / "status.json").read_text())["calibration_warning"] is None


def test_req_ing_snap_2_status_says_segments_available_only_when_the_sam_file_is_in_raw(tmp_path):
    """REQ-ING-SNAP.1-2: with the SAM file the full run snaps and status says available; without it, missing plus an anomaly."""
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "d1", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    st = json.loads((out / "status.json").read_text())
    assert st["segments"] == "missing" and any("segments unavailable" in a for a in st["anomalies"])
    street = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"SEGMENT_ID": 7, "F_ZLEV": 0, "T_ZLEV": 0},
         "geometry": {"type": "LineString", "coordinates": [[-71.1405, 42.27], [-71.1395, 42.27]]}},
        {"type": "Feature", "properties": {"SEGMENT_ID": 8, "F_ZLEV": 0, "T_ZLEV": 0},
         "geometry": {"type": "LineString", "coordinates": [[-71.1395, 42.27], [-71.1395, 42.2709]]}}]}  # fmt: skip
    (raw / "street_segments_sam.geojson").write_text(json.dumps(street))
    out2 = tmp_path / "out2"
    rep = run_pipeline(out_dir=out2, raw_dir=raw, work_dir=tmp_path / "d2", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    st2 = json.loads((out2 / "status.json").read_text())
    assert st2["segments"] == "available" and not any("segments unavailable" in a for a in st2["anomalies"])
    assert rep.row_counts["intersections"] == 1 and rep.row_counts["snapped_cases"] >= 2
    assert [z["zombie_id"] for z in json.loads((out2 / "zombies.json").read_text())["zombies"]] == ["1001:1002"]
    assert json.loads((out2 / "zombies.json").read_text())["zombies"][0]["match_mode"] == "segment"


def test_req_stat_exp_1_a_missing_stats_submodule_fails_and_absent_stats_removes_stale_files(tmp_path, monkeypatch):
    """REQ-STAT-EXP.1 (ops#48): a missing module inside the stats package is an error; "not present" removes old stats files."""
    import importlib

    real = importlib.import_module

    def absent(name, *a, **k):
        if name == "undead311.stats.pipeline":
            raise ModuleNotFoundError("No module named 'undead311.stats.pipeline'", name="undead311.stats.pipeline")
        return real(name, *a, **k)

    def inner(name, *a, **k):
        if name == "undead311.stats.pipeline":
            raise ModuleNotFoundError("No module named 'undead311.stats.credibility'", name="undead311.stats.credibility")
        return real(name, *a, **k)

    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(importlib, "import_module", inner)
    with pytest.raises(ModuleNotFoundError, match="credibility"):
        run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap)
    (out / "stats").mkdir(parents=True, exist_ok=True)
    for name in ("scorecard.json", "judge_tour.json", "stats_status.json"):
        (out / "stats" / name).write_text("{}")
    monkeypatch.setattr(importlib, "import_module", absent)
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert rep.stats == "not present"
    assert not any((out / "stats" / n).exists() for n in ("scorecard.json", "judge_tour.json", "stats_status.json"))


def test_req_stat_exp_1_stats_files_and_status_say_sample_or_full(tmp_path):
    """REQ-STAT-EXP.1 (ops#51): scorecard.json, judge_tour.json and status.json carry `dataset`, so the web can label it."""
    out = tmp_path / "out"
    run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "data", run_time="2026-11-13T00:00:00Z", grid=False)
    assert json.loads((out / "status.json").read_text())["dataset"] == "sample"
    assert json.loads((out / "stats" / "scorecard.json").read_text())["dataset"] == "sample"
    assert json.loads((out / "stats" / "stats_status.json").read_text())["dataset"] == "sample"
    if (out / "stats" / "judge_tour.json").exists():
        assert json.loads((out / "stats" / "judge_tour.json").read_text())["dataset"] == "sample"
    raw, snap = raw_folder(tmp_path)
    full = tmp_path / "full"
    run_pipeline(out_dir=full, raw_dir=raw, work_dir=tmp_path / "data2", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert json.loads((full / "status.json").read_text())["dataset"] == "full"
    assert json.loads((full / "stats" / "scorecard.json").read_text())["dataset"] == "full"


def test_req_stat_sf_1_a_missing_on_time_column_is_a_status_anomaly(tmp_path):
    """REQ-STAT-SF.1 (ops#49): the tiny raw folder has no on_time column, so status.json says so; the sample has it."""
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "data", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    anomalies = json.loads((out / "status.json").read_text())["anomalies"]
    assert any("on_time is known for 0 of 1 closed in-scope legacy-system cases" in a for a in anomalies)
    sample_out = tmp_path / "s"
    run_pipeline(sample=True, out_dir=sample_out, work_dir=tmp_path / "data3", run_time="2026-11-13T00:00:00Z", grid=False)
    assert not any("on_time is known" in a for a in json.loads((sample_out / "status.json").read_text())["anomalies"])


def test_req_stat_sf_4_sample_scorecard_has_on_time_rates(tmp_path):
    """REQ-STAT-SF.1, .4: on the committed sample the citywide two-number scorecard has known on-time cases, not no_cases."""
    out = tmp_path / "out"
    run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "data", run_time="2026-11-13T00:00:00Z", grid=False)
    cards = json.loads((out / "stats" / "scorecard.json").read_text())["scorecards"]
    city = {c["tier_set"]: c for c in cards if c["family"] == "citywide"}
    for tier_set in ("headline", "all"):
        c = city[tier_set]
        assert c["n_on_time_known"] > 0 and c["on_time"]["rate"] is not None and c["on_time"]["reason"] is None
        assert c["stayed_fixed_raw"]["rate"] is not None
        assert c["stayed_fixed_raw"]["rate"] <= c["on_time"]["rate"]
