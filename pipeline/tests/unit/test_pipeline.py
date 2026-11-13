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
    assert rep.tier_counts == {"headline": 1, "source_unknown": 0, "sensitivity": 0}
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
