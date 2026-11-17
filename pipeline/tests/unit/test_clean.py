"""REQ-ING-CLEAN.1-4: coordinates, placeholders, out-of-scope types, counts by reason."""

from __future__ import annotations

import duckdb

from undead311.ingest.clean import clean, ids_by_reason
from undead311.ingest.crosswalk import apply_crosswalk

ROWS = [
    # id, system, type_raw, lat, lon, open time
    ("ok", "legacy", "Request for Pothole Repair", 42.30, -71.10, "2024-01-01 12:00:00"),
    ("nullc", "legacy", "Request for Pothole Repair", None, -71.10, "2024-01-01 12:00:00"),
    ("oob", "legacy", "Request for Pothole Repair", 42.00, -72.00, "2024-01-01 12:00:00"),
    ("ph1", "legacy", "Request for Pothole Repair", 42.3603, -71.0583, "2024-01-01 12:00:00"),
    ("ph2", "new", "Pothole", 42.35951, -71.05879, "2025-09-01 12:00:00"),
    ("near", "legacy", "Request for Pothole Repair", 42.3594, -71.0587, "2024-01-01 12:00:00"),
    ("graf", "legacy", "Graffiti Removal", 42.30, -71.10, "2024-01-01 12:00:00"),
    ("unl", "legacy", "A Type Nobody Listed", 42.30, -71.10, "2024-01-01 12:00:00"),
    ("both", "legacy", "Graffiti Removal", None, None, "2024-01-01 12:00:00"),
    ("notime", "legacy", "Request for Pothole Repair", 42.30, -71.10, None),
]


def make() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        "create table cases_norm(id varchar, system varchar, type_raw varchar, lat double, lon double, "
        "open_time_utc timestamp, closure_text varchar)"
    )
    con.executemany("insert into cases_norm select ?, ?, ?, ?, ?, try_cast(? as timestamp), NULL", ROWS)
    apply_crosswalk(con)
    return con


def test_req_ing_clean_1_drops_bad_coordinates_placeholders_and_out_of_scope_types():
    """REQ-ING-CLEAN.1-2: each reason has the right IDs; a case with two problems gets the first reason only."""
    con = make()
    report = clean(con)
    ids = ids_by_reason(con)
    assert ids["null_coords"] == ["nullc"]
    assert ids["out_of_bounds"] == ["oob"]
    assert ids["placeholder"] == ["ph1", "ph2"]  # both placeholder points, rounded to 4 decimals
    assert ids["excluded_type"] == ["both", "graf"]  # type is tested before coordinates
    assert ids["unlisted_type"] == ["unl"]
    assert ids["null_open_time"] == ["notime"]
    kept = [r[0] for r in con.execute("select id from cases_clean order by id").fetchall()]
    assert kept == ["near", "ok"]  # 42.3594,-71.0587 is not a placeholder (data dictionary)
    assert report.kept == 2


def test_req_ing_clean_3_counts_by_reason_family_and_system():
    """REQ-ING-CLEAN.3: every exclusion is counted by reason, family and system."""
    con = make()
    report = clean(con)
    assert report.counts == {
        "unlisted_type": 1, "excluded_type": 2, "null_coords": 1, "out_of_bounds": 1, "placeholder": 2,
        "null_open_time": 1, "test_data": 0,
    }  # fmt: skip
    rows = {(r["reason"], r["type_family"], r["system"]): r["n"] for r in report.by_family_system}
    assert rows[("placeholder", "pothole_roadway", "new")] == 1
    assert rows[("excluded_type", "graffiti", "legacy")] == 2
    assert rows[("unlisted_type", "unlisted", "legacy")] == 1
    assert sum(report.counts.values()) + report.kept == len(ROWS)  # nothing vanishes


def test_req_ing_clean_4_candidate_placeholders_are_reported_not_dropped():
    """REQ-ING-CLEAN.4: a point shared by more than 200 cases is listed and kept."""
    con = duckdb.connect()
    con.execute(
        "create table cases_norm(id varchar, system varchar, type_raw varchar, lat double, lon double, "
        "open_time_utc timestamp, closure_text varchar)"
    )
    rows = [(f"c{i}", "legacy", "Sign Repair", 42.31, -71.11, "2024-01-01 12:00:00", None) for i in range(201)]
    rows += [(f"d{i}", "legacy", "Sign Repair", 42.32, -71.12, "2024-01-01 12:00:00", None) for i in range(200)]
    con.executemany("insert into cases_norm select ?, ?, ?, ?, ?, try_cast(? as timestamp), ? ", rows)
    apply_crosswalk(con)
    report = clean(con)
    assert report.candidate_placeholders == [{"lat": 42.31, "lon": -71.11, "n": 201}]
    assert report.kept == 401
