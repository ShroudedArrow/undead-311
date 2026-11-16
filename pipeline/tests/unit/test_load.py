"""REQ-ING-1.1-3: raw CSVs into DuckDB, a clear error for a missing file."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from undead311.ingest.load import RawFileMissing, expected_files, load

LEGACY_HEAD = "case_enquiry_id,open_dt,closed_dt,case_status,closure_reason,type,latitude,longitude\n"
NEW_HEAD = "case_id,longitude,latitude,open_date,close_date,case_status,closure_reason,service_name\n"


def _raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "311_2015.csv").write_text(LEGACY_HEAD + "1,2015-01-01 08:00:00,,Open,,Sign Repair,42.3,-71.1\n")
    (raw / "311_2016.csv").write_text(
        LEGACY_HEAD
        + '2,2016-01-01 08:00:00,2016-01-02 08:00:00,Closed,"Case Closed, with a comma",Sign Repair,42.3,-71.1\n'
        + '3,2016-02-01 08:00:00,,Open,"multi\nline",Sign Repair,42.3,-71.1\n'
    )
    (raw / "311_new_system.csv").write_text(
        NEW_HEAD + "BCS-00000001,-71.1,42.3,2025-08-02 09:00:00+00,,In progress,,Pothole\n"
    )
    return raw


def test_req_ing_1_1_loads_both_systems_with_row_counts_per_file(tmp_path):
    """REQ-ING-1.1: raw_legacy and raw_new exist; row counts are recorded per file; all columns are text."""
    con = duckdb.connect()
    report = load(con, _raw(tmp_path))
    assert (report.legacy_rows, report.new_rows) == (3, 1)
    assert report.rows_by_file == {"311_2015.csv": 1, "311_2016.csv": 2, "311_new_system.csv": 1}
    types = {r[0]: r[1] for r in con.execute("select column_name, data_type from information_schema.columns "
                                              "where table_name = 'raw_legacy'").fetchall()}
    assert types["case_enquiry_id"] == "VARCHAR" and types["latitude"] == "VARCHAR"
    assert con.execute("select count(*) from raw_legacy where closure_reason like '%comma%'").fetchone()[0] == 1


def test_req_ing_1_1_new_system_column_order_is_read_by_name(tmp_path):
    """REQ-ING-1.1 / data-dictionary: the new file lists longitude before latitude; columns are read by name."""
    con = duckdb.connect()
    load(con, _raw(tmp_path))
    assert con.execute("select latitude, longitude from raw_new").fetchone() == ("42.3", "-71.1")


def test_req_ing_1_2_missing_file_names_the_file_and_the_download_command(tmp_path):
    """REQ-ING-1.2: a file listed in SNAPSHOT.md but missing stops the run with its name and `make data-download`."""
    raw = _raw(tmp_path)
    snap = tmp_path / "SNAPSHOT.md"
    snap.write_text(
        "| file | resource |\n|---|---|\n| 311_2015.csv | a |\n| 311_2016.csv | b |\n| 311_2017.csv | c |\n"
        "| 311_new_system.csv | d |\n"
    )
    assert expected_files(snap) == ["311_2015.csv", "311_2016.csv", "311_2017.csv", "311_new_system.csv"]
    with pytest.raises(RawFileMissing) as exc:
        load(duckdb.connect(), raw, snap)
    assert "311_2017.csv" in str(exc.value) and "make data-download" in str(exc.value)


def test_req_ing_1_2_empty_raw_folder_stops_with_download_hint(tmp_path):
    """REQ-ING-1.2: no raw files at all is a clear error, not an empty database."""
    empty = tmp_path / "raw"
    empty.mkdir()
    with pytest.raises(RawFileMissing, match="make data-download"):
        load(duckdb.connect(), empty)


def test_req_ing_1_2_repo_snapshot_lists_the_thirteen_files():
    """REQ-ING-1.2: the committed SNAPSHOT.md lists 12 legacy years (2015-2026) plus the new-system file."""
    names = expected_files(Path(__file__).resolve().parents[3] / "data" / "SNAPSHOT.md")
    assert len(names) == 13 and "311_new_system.csv" in names and "311_2026.csv" in names
