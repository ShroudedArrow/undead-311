"""REQ-DET-MATCH.1-5 and REQ-ING-SNAP.4: segment, intersection and radius matching."""

from __future__ import annotations

import pytest
from helpers import mk, params

from undead311.detect.match import distance_m, is_snapped, match


def test_req_det_match_1_same_segment_within_75m_is_segment_mode():
    """REQ-DET-MATCH.1: same segment, 70 m apart -> segment."""
    m = match(mk("a", 0, 1, segment="S", x=0), mk("b", 2, segment="S", x=70))
    assert m.mode == "segment" and m.distance_m == pytest.approx(70, abs=0.5)


def test_req_det_match_1_opposite_ends_of_a_long_segment_never_match():
    """REQ-DET-MATCH.1/.3: same segment but 100 m apart: no match, not even by radius (and not at 29 m by radius)."""
    assert match(mk("a", 0, 1, segment="S", x=0), mk("b", 2, segment="S", x=100)) is None
    assert match(mk("a", 0, 1, segment="S", x=0), mk("b", 2, segment="S", x=76)) is None


def test_req_det_match_3_snapped_cases_on_different_segments_never_match_by_radius():
    """REQ-DET-MATCH.3: 10 m apart on different segments, no shared intersection -> no match."""
    assert match(mk("a", 0, 1, segment="S1", x=0), mk("b", 2, segment="S2", y=10)) is None


def test_req_det_match_2_three_way_intersection_14m_matches_and_16m_does_not():
    """REQ-DET-MATCH.2, REQ-ING-SNAP.4: both within 15 m of one node match; one at 16 m has no near node."""
    node = "N1"
    a = mk("a", 0, 1, segment="S1", x=-14, nodes=((node, 14.0),))
    b = mk("b", 2, segment="S2", y=14, nodes=((node, 14.0),))
    c = mk("c", 2, segment="S3", x=16)  # 16 m from the node: no near_nodes entry
    m = match(a, b)
    assert m.mode == "intersection" and m.distance_m == pytest.approx(28.0)
    assert match(a, c) is None
    assert match(b, c) is None


def test_req_det_match_2_node_distance_over_15_is_not_an_intersection_match():
    """REQ-DET-MATCH.2: a stale near_nodes entry above INTERSECTION_M is ignored."""
    a = mk("a", 0, 1, segment="S1", nodes=(("N", 15.5),))
    b = mk("b", 2, segment="S2", nodes=(("N", 3.0),))
    assert match(a, b) is None


def test_req_det_match_3_radius_only_when_a_case_is_unsnapped():
    """REQ-DET-MATCH.3: one unsnapped case, 25 m apart -> radius; 35 m -> none."""
    snapped = mk("a", 0, 1, segment="S", x=0)
    near, far = mk("b", 2, x=25), mk("c", 2, x=35)
    assert match(snapped, near).mode == "radius"
    assert match(snapped, far) is None
    assert match(near, mk("d", 2, x=0)).mode == "radius"  # both unsnapped


def test_req_ing_snap_1_a_case_snapped_beyond_15m_counts_as_unsnapped():
    """REQ-ING-SNAP.1: segment_snap_m above SEGMENT_SNAP_M means not snapped."""
    far_snap = mk("a", 0, 1, segment="S", snap=16.0)
    assert not is_snapped(far_snap) and is_snapped(mk("b", 0, segment="S", snap=15.0))
    assert match(far_snap, mk("c", 2, segment="S", x=20)).mode == "radius"


def test_req_det_match_5_radius_matching_mode_ignores_segments_and_nodes():
    """REQ-DET-MATCH.5: in `radius` mode every pair uses RADIUS_M, even snapped cases on different segments."""
    p = params(matching="radius", RADIUS_M=15)
    a, b = mk("a", 0, 1, segment="S1", x=0), mk("b", 2, segment="S2", x=10)
    assert match(a, b, p).mode == "radius"
    assert match(a, mk("c", 2, segment="S1", x=20), p) is None  # same segment, but beyond the 15 m radius
    assert match(a, mk("d", 2, segment="S2", x=20), params(matching="radius", RADIUS_M=50)).mode == "radius"


def test_req_det_match_4_distance_is_haversine_in_meters():
    """REQ-DET-MATCH.4: one degree of latitude is about 111.2 km."""
    assert distance_m(42.0, -71.0, 43.0, -71.0) == pytest.approx(111_195, rel=1e-3)
    assert distance_m(42.3, -71.1, 42.3, -71.1) == 0.0
