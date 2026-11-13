"""REQ-DET-MATCH.4: the SQL grid-bucket edge generator equals the brute-force generator."""

from __future__ import annotations

from pathlib import Path

import duckdb
from helpers import mk, params

from undead311.detect.cases import cases_from_sample_csv
from undead311.detect.edges import brute_edges, sql_edges, time_related

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample_311.csv"


def test_req_det_match_4_sql_edges_equal_brute_force_edges_on_the_sample():
    """REQ-DET-MATCH.4: on data/sample the SQL edges (grid join) and the brute-force edges are identical."""
    cases = cases_from_sample_csv(SAMPLE)
    assert len(cases) > 10_000
    brute = brute_edges(cases)
    sql = sql_edges(duckdb.connect(), cases)
    assert len(brute) > 100  # the sample was built from candidate pairs, so edges exist
    assert {k: (v.mode, round(v.distance_m, 6)) for k, v in sql.items()} == {
        k: (v.mode, round(v.distance_m, 6)) for k, v in brute.items()
    }
    assert {v.mode for v in brute.values()} == {"radius"}  # the sample has no segment columns


def test_req_det_match_4_sql_edges_equal_brute_force_with_segments_and_other_params():
    """REQ-DET-MATCH.4: segment and intersection modes and a bigger radius agree between the two generators."""
    cases = [
        mk("a", 0, 1, segment="S1", x=0), mk("b", 2, segment="S1", x=70), mk("c", 2, segment="S1", x=90),
        mk("d", 0, 1, segment="S2", x=-14, nodes=(("N", 14.0),)), mk("e", 2, segment="S3", y=14, nodes=(("N", 14.0),)),
        mk("f", 3, x=200), mk("g", 4, 5, x=225), mk("h", 6, x=250, system="new"), mk("i", 0, 1, x=0, family="sign"),
    ]  # fmt: skip
    for p in (params(), params(RADIUS_M=50), params(matching="radius", RADIUS_M=15), params(WINDOW_DAYS=2)):
        b = brute_edges(cases, p)
        s = sql_edges(duckdb.connect(), cases, p)
        assert {k: (v.mode, round(v.distance_m, 6)) for k, v in s.items()} == {
            k: (v.mode, round(v.distance_m, 6)) for k, v in b.items()
        }
    assert ("a", "b") in brute_edges(cases) and ("a", "c") not in brute_edges(cases)
    assert brute_edges(cases)[("d", "e")].mode == "intersection"


def test_req_det_match_4_time_conditions_are_exact_at_the_boundaries():
    """REQ-DET-2.1 / MATCH.4: R must open strictly after the close, and at most WINDOW_DAYS after it."""
    orig = mk("o", 0, 1)
    assert not time_related(orig, mk("r", 1))  # opens exactly at the close: not a re-report ...
    assert time_related(orig, mk("r2", 1, open_hours=0.001))
    # an edge reaches WINDOW_DAYS + INCIDENT_MAX_SPAN_DAYS (the incident may close 7 days after this member);
    # the detector applies the exact 60-day window against the incident's close time
    assert time_related(orig, mk("r3", 68))
    assert not time_related(orig, mk("r4", 68, open_hours=0.01))
