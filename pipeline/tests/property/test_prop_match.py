"""Properties P6 (distance), P21 (the matching rule over generated towns) and P22 (symmetry).

REQ-DET-MATCH.1-4, REQ-ING-SNAP.4, testing.md #11.
"""

from __future__ import annotations

import math

from helpers import at, mk
from hypothesis import given
from hypothesis import strategies as st

from undead311.detect.match import distance_m, is_snapped, match

lats = st.floats(42.2, 42.45, allow_nan=False)
lons = st.floats(-71.2, -70.9, allow_nan=False)


@given(lats, lons, lats, lons)
def test_prop_p6_distance_is_symmetric_nonnegative_and_zero_on_identical_points(a, b, c, d):
    """REQ-DET-MATCH.4: d(a,b) = d(b,a) >= 0 and d(a,a) = 0."""
    assert distance_m(a, b, c, d) >= 0
    assert math.isclose(distance_m(a, b, c, d), distance_m(c, d, a, b), rel_tol=1e-12, abs_tol=1e-9)
    assert distance_m(a, b, a, b) == 0.0


# --- generated towns -------------------------------------------------------------------------------------------
# A town has a few intersections (nodes). Streets are arbitrary segment labels; a case is on a segment (snapped),
# near-snapped (snap > 15 m, so unsnapped), or off-network. An overpass is a crossing that is NOT in `nodes`;
# a dead end is a segment end that is NOT in `nodes`; a mid-block split IS a node (a shared endpoint).
node_points = st.lists(st.tuples(st.floats(-60, 60), st.floats(-60, 60)), min_size=0, max_size=3)
segments = st.sampled_from(["S1", "S2", "S3", "S4", None])


@st.composite
def town_cases(draw):
    nodes = [(f"N{i}", x, y) for i, (x, y) in enumerate(draw(node_points))]
    out = []
    for i in range(2):
        x, y = draw(st.floats(-90, 90)), draw(st.floats(-90, 90))
        seg = draw(segments)
        snap = draw(st.sampled_from([2.0, 14.9, 15.0, 15.1, 30.0]))
        near = ()
        if seg is not None and snap <= 15:
            near = tuple(
                sorted((n, math.hypot(x - nx, y - ny)) for n, nx, ny in nodes if math.hypot(x - nx, y - ny) <= 15)
            )
        out.append(mk(f"c{i}", 0, 1, x=x, y=y, segment=seg, snap=snap, nodes=near))
    return out


@given(town_cases())
def test_prop_p21_matching_rule_over_generated_towns(pair):
    """REQ-DET-MATCH.1-3: the three-mode rule, exactly as written in zombie-definition.md."""
    a, b = pair
    m = match(a, b)
    d = distance_m(a.lat, a.lon, b.lat, b.lon)
    both_snapped = is_snapped(a) and is_snapped(b)
    if both_snapped and a.segment_id == b.segment_id:
        assert (m is not None) == (d <= 75)
        assert m is None or m.mode == "segment"
    elif both_snapped:
        # different segments: only the intersection mode, never radius
        assert m is None or m.mode == "intersection"
        shared = {n for n, _ in a.near_nodes} & {n for n, _ in b.near_nodes}
        assert (m is not None) == bool(shared)
        if m is not None:
            assert all(dist <= 15 for _, dist in a.near_nodes + b.near_nodes if _ in shared)
    else:
        assert (m is not None) == (d <= 30)
        assert m is None or m.mode == "radius"
    assert m is None or m.mode != "radius" or not both_snapped


@given(town_cases())
def test_prop_p22_matching_is_symmetric(pair):
    """REQ-DET-MATCH.4: match(a, b) and match(b, a) agree on mode and distance."""
    a, b = pair
    ab, ba = match(a, b), match(b, a)
    assert (ab is None) == (ba is None)
    if ab is not None:
        assert ab.mode == ba.mode and math.isclose(ab.distance_m, ba.distance_m, abs_tol=1e-9)


def test_prop_p21_placement_helper_is_consistent():
    """REQ-DET-MATCH.4: the helper that places test cases in meters is accurate to 1 m at 100 m."""
    la, lo = at(0, 0)
    lb, lob = at(100, 0)
    assert abs(distance_m(la, lo, lb, lob) - 100) < 1
