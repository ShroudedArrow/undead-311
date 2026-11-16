"""REQ-STAT-SF.1 (ops#49): on_time coverage anomalies."""

from __future__ import annotations

import duckdb
from hypothesis import given
from hypothesis import strategies as st

from undead311.ingest.quality import ON_TIME_MIN_KNOWN_SHARE, on_time_anomalies, on_time_coverage


def table(rows):
    con = duckdb.connect()
    con.execute("create table cases_clean(system varchar, status varchar, close_time_utc timestamp, scope_tier varchar, on_time boolean)")
    for r in rows:
        con.execute("insert into cases_clean values (?,?,?,?,?)", r)
    return con


def test_req_stat_sf_1_coverage_counts_closed_in_scope_cases_per_system():
    t = "2024-01-02 00:00:00"
    con = table([("legacy", "Closed", t, "core", None), ("legacy", "Closed", t, "core", True),
                 ("legacy", "Open", None, "core", None), ("new", "Closed", t, "sensitivity", False),
                 ("new", "Closed", t, "excluded", None)])  # fmt: skip
    assert on_time_coverage(con) == {"legacy": (1, 2), "new": (1, 1)}


def test_req_stat_sf_1_a_system_below_the_threshold_is_flagged_and_names_the_counts():
    found = on_time_anomalies({"legacy": (0, 100), "new": (95, 100)})
    assert len(found) == 1 and "0 of 100" in found[0] and "legacy" in found[0]
    assert on_time_anomalies({"legacy": (0, 0)}) == []


@given(st.integers(0, 500), st.integers(0, 500))
def test_req_stat_sf_1_threshold_is_exact(known, extra):
    closed = known + extra
    flagged = bool(on_time_anomalies({"s": (known, closed)}))
    assert flagged == (closed > 0 and known / closed < ON_TIME_MIN_KNOWN_SHARE)
