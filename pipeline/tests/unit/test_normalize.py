"""REQ-ING-2.1-3 and REQ-ING-TZ.1-3: the normalized schema, counted nulls, times through times.py."""

from __future__ import annotations

import duckdb

from undead311.ingest.normalize import NORM_COLUMNS, normalize, time_udf

LEGACY_DDL = (
    "create table raw_legacy(case_enquiry_id varchar, open_dt varchar, closed_dt varchar, case_status varchar, "
    "closure_reason varchar, type varchar, department varchar, neighborhood varchar, pwd_district varchar, "
    "location_street_name varchar, latitude varchar, longitude varchar, source varchar, ontime varchar, "
    "filename varchar)"
)
NEW_DDL = (
    "create table raw_new(case_id varchar, open_date varchar, close_date varchar, case_status varchar, "
    "closure_reason varchar, closure_comments varchar, service_name varchar, assigned_department varchar, "
    "neighborhood varchar, public_works_district varchar, street_name varchar, latitude varchar, longitude varchar, "
    "report_source varchar, on_time varchar, filename varchar)"
)


def make_con(legacy: list[tuple], new: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(LEGACY_DDL)
    con.execute(NEW_DDL)
    if legacy:
        con.executemany("insert into raw_legacy values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", legacy)
    if new:
        con.executemany("insert into raw_new values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", new)
    return con


L1 = ("1001", "2024-03-04 09:12:00", "2024-03-06 14:30:00", "Closed", "Case Closed Resolved", "Sign Repair",
      "PWDx", "Dorchester", "10B", "Test St", "42.27", "-71.14", "Citizens Connect App", "ONTIME", "311_2024.csv")  # fmt: skip
N1 = ("BCS-00000001", "2026-07-16 16:10:24.446642+00", "2026-07-17 08:00:00+00", "Closed", "Resolved",
      "completed by task", "Pothole", "Public Works Department (PWD)", "Allston", "5", "Main St", "42.35", "-71.13",
      "BOS311", "OVERDUE", "311_new_system.csv")  # fmt: skip


def test_req_ing_2_1_maps_both_systems_to_one_schema():
    """REQ-ING-2.1: one table, `system` and `closure_code` set; new-system text = comments else code."""
    con = make_con([L1], [N1])
    normalize(con)
    cols = [r[0] for r in con.execute("describe cases_norm").fetchall()]
    assert tuple(cols) == NORM_COLUMNS
    rows = {r[0]: r for r in con.execute("select id, system, closure_text, closure_code, department, district, "
                                         "source, on_time from cases_norm").fetchall()}
    assert rows["1001"][1:] == ("legacy", "Case Closed Resolved", None, "PWDx", "10B", "Citizens Connect App", True)
    assert rows["BCS-00000001"][1:] == ("new", "completed by task", "Resolved", "Public Works Department (PWD)", "5",
                                        "BOS311", False)


def test_req_ing_tz_1_both_systems_are_boston_wall_clock_and_plus00_is_ignored():
    """REQ-ING-TZ.1: 16:10 EDT on 2026-07-16 is 20:10 UTC even though the new system says +00."""
    con = make_con([L1], [N1])
    normalize(con)
    assert con.execute("select open_time_utc, open_time_local from cases_norm where id = 'BCS-00000001'").fetchone() == (
        __import__("datetime").datetime(2026, 7, 16, 20, 10, 24, 446642),
        __import__("datetime").datetime(2026, 7, 16, 16, 10, 24, 446642),
    )
    assert con.execute("select open_time_utc from cases_norm where id = '1001'").fetchone()[0].hour == 14  # EST->UTC


def test_req_ing_tz_2_fall_back_hour_is_flagged_ambiguous_and_gap_is_nonexistent():
    """REQ-ING-TZ.2: first occurrence used and flagged; the spring-forward gap is shifted and flagged."""
    legacy = [
        ("A", "2024-11-03 01:30:00", None, "Open", None, "Sign Repair", None, None, None, None, "42.3", "-71.1", None, None, "f"),
        ("B", "2024-03-10 02:30:00", None, "Open", None, "Sign Repair", None, None, None, None, "42.3", "-71.1", None, None, "f"),
    ]  # fmt: skip
    con = make_con(legacy, [])
    normalize(con)
    got = {r[0]: r[1:] for r in con.execute("select id, open_time_utc, local_ambiguous, local_nonexistent "
                                            "from cases_norm").fetchall()}
    assert got["A"][0].hour == 5 and got["A"][1] is True and got["A"][2] is False  # EDT: 01:30 -> 05:30 UTC
    assert got["B"][1] is False and got["B"][2] is True


def test_req_ing_2_2_unparseable_values_become_null_and_are_counted_by_reason():
    """REQ-ING-2.2: bad time, bad coordinate, duplicate id, closed without close time and close before open."""
    legacy = [
        ("C1", "not a time", None, "Open", None, "Sign Repair", None, None, None, None, "42.3", "-71.1", None, None, "f1"),
        ("C2", "2024-01-01 08:00:00", None, "Closed", None, "Sign Repair", None, None, None, None, "abc", "-71.1", None, None, "f1"),
        ("C3", "2024-01-05 08:00:00", "2024-01-04 08:00:00", "Closed", None, "Sign Repair", None, None, None, None, "42.3", "-71.1", None, None, "f1"),
        ("C4", "2024-01-01 08:00:00", None, "Open", None, "Sign Repair", None, None, None, None, "42.3", "-71.1", None, None, "f1"),
        ("C4", "2024-01-01 08:00:00", None, "Open", None, "Sign Repair", None, None, None, None, "42.3", "-71.1", None, None, "f2"),
    ]  # fmt: skip
    con = make_con(legacy, [])
    report = normalize(con)
    assert report.issues["unparseable_open_time"] == 1
    assert report.issues["unparseable_coordinate"] == 1
    assert report.issues["closed_without_close_time"] == 1
    assert report.issues["close_before_open"] == 1
    assert report.issues["duplicate_id"] == 1
    assert con.execute("select open_time_utc is null, lat is null from cases_norm where id = 'C1'").fetchone() == (True, False)
    assert con.execute("select lat is null from cases_norm where id = 'C2'").fetchone() == (True,)
    assert con.execute("select count(*) from cases_norm").fetchone()[0] == 4  # C1 is kept with a null time
    assert dict(con.execute("select reason, n from norm_issues").fetchall())["duplicate_id"] == 1


def test_req_ing_tz_time_udf_contract():
    """REQ-ING-TZ.1-2: empty -> None, garbage -> ERR marker, wall-clock -> 'utc|local|flags'."""
    assert time_udf("legacy", "") is None and time_udf("new", None) is None
    assert time_udf("legacy", "garbage") == "!ERR"
    assert time_udf("legacy", "2024-07-01 12:00:00") == "2024-07-01 16:00:00|2024-07-01 12:00:00|"
    assert time_udf("new", "2024-11-03 01:15:00+00").endswith("|local_ambiguous")


def test_req_stat_sf_1_legacy_on_time_and_target_are_read_under_either_header_spelling():
    """REQ-STAT-SF.1: the yearly legacy files say `on_time` and `sla_target_dt`; an older header said `ontime`, `target_dt`."""
    for on_col, target_col in (("on_time", "sla_target_dt"), ("ontime", "target_dt")):
        con = duckdb.connect()
        con.execute(
            f"create table raw_legacy(case_enquiry_id varchar, open_dt varchar, {target_col} varchar, closed_dt varchar, "
            f"{on_col} varchar, case_status varchar, type varchar, filename varchar)"
        )
        con.execute(
            "insert into raw_legacy values ('1', '2024-03-04 09:12:00', '2024-03-08 09:12:00', '2024-03-06 14:30:00', "
            "'ONTIME', 'Closed', 'Sign Repair', 'f'), ('2', '2024-03-04 09:12:00', NULL, '2024-03-20 14:30:00', "
            "'OVERDUE', 'Closed', 'Sign Repair', 'f')"
        )
        con.execute(NEW_DDL)
        normalize(con)
        got = con.execute("select id, on_time, target_time_utc is not null from cases_norm order by id").fetchall()
        assert got == [("1", True, True), ("2", False, False)]
