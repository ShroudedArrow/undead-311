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


# --- P21 variant: towns built from segment GeoJSON, so build_intersections and snap_cases are in the path --------
# REQ-DET-MATCH.1-3, REQ-ING-SNAP.1, REQ-ING-SNAP.4 (ops#81). The rule is checked on the DERIVED segment_id and near_nodes.

import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import duckdb  # noqa: E402
from hypothesis import HealthCheck, settings  # noqa: E402

from undead311.detect.cases import cases_from_table  # noqa: E402
from undead311.ingest.snap import snap_cases  # noqa: E402

M_LAT = 111_320.0
LAT0, LON0 = 42.33, -71.08
M_LON = M_LAT * math.cos(math.radians(LAT0))


def _pt(e: float, n: float) -> list[float]:
    return [LON0 + e / M_LON, LAT0 + n / M_LAT]


def _feat(sid: int, a: tuple[float, float], b: tuple[float, float], f: int = 0, t: int = 0) -> dict:
    return {"type": "Feature", "properties": {"SEGMENT_ID": sid, "F_ZLEV": f, "T_ZLEV": t},
            "geometry": {"type": "LineString", "coordinates": [_pt(*a), _pt(*b)]}}  # fmt: skip


def _town(kind: str) -> list[dict]:
    """crossing: two streets, each split at the origin (4 segments, one intersection).
    overpass: a ground street and an elevated street end at the same point but at different z-levels (no node).
    dead_end: two streets whose ends meet at the origin with only one segment each side of a T (the stem is the only
    segment at its end; the bar is not split there), so no endpoint is shared."""
    if kind == "crossing":
        return [_feat(1, (-200, 0), (0, 0)), _feat(2, (0, 0), (200, 0)), _feat(3, (0, -200), (0, 0)),
                _feat(4, (0, 0), (0, 200))]  # fmt: skip
    if kind == "overpass":
        return [_feat(1, (-200, 0), (0, 0), 0, 0), _feat(2, (0, 0), (0, 200), 1, 1)]
    return [_feat(1, (-200, 0), (200, 0)), _feat(2, (0, 0), (0, 200))]  # dead_end: a T whose bar is not split


def _derived(kind: str, pts: list[tuple[float, float]]):
    """Snap `pts` (east, north metres) onto the generated town; return the loaded cases."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "s.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": _town(kind)}))
        con = duckdb.connect()
        con.execute("create table cases_clean(id varchar, system varchar, lat double, lon double, scope_tier varchar, "
                    "segment_id varchar, segment_snap_m double, open_time_utc timestamp, type_family varchar)")  # fmt: skip
        for i, (e, n) in enumerate(pts):
            lon, lat = _pt(e, n)
            con.execute("insert into cases_clean values (?,?,?,?,?,?,?,'2024-01-01','pothole_roadway')",
                        [f"c{i}", "legacy", lat, lon, "core", None, None])  # fmt: skip
        snap_cases(con, path)
        return {c.id: c for c in cases_from_table(con)}


spot = st.tuples(st.floats(-45, 45), st.floats(-45, 45))


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.sampled_from(["crossing", "overpass", "dead_end"]), spot, spot)
def test_prop_p21_derived_intersections_obey_the_three_mode_rule(kind, p1, p2):
    """REQ-DET-MATCH.1-3, REQ-ING-SNAP.4: over generated segment towns the rule holds on the derived near_nodes, and
    overpass and dead-end towns never produce an intersection match."""
    cases = _derived(kind, [p1, p2])
    a, b = cases["c0"], cases["c1"]
    m = match(a, b)
    d = distance_m(a.lat, a.lon, b.lat, b.lon)
    if is_snapped(a) and is_snapped(b):
        if a.segment_id == b.segment_id:
            assert (m is not None) == (d <= 75) and (m is None or m.mode == "segment")
        else:
            assert m is None or m.mode == "intersection"
            assert (m is not None) == bool({n for n, _ in a.near_nodes} & {n for n, _ in b.near_nodes})
    else:
        assert (m is not None) == (d <= 30) and (m is None or m.mode == "radius")
    if kind != "crossing":
        assert not a.near_nodes and not b.near_nodes  # an overpass or a dead end is never an intersection
        assert m is None or m.mode != "intersection"
    else:
        r1, r2 = math.hypot(*p1), math.hypot(*p2)
        if is_snapped(a) and is_snapped(b) and a.segment_id != b.segment_id:
            if max(r1, r2) <= 14.5:
                assert m is not None and m.mode == "intersection"
            if max(r1, r2) > 15.5:
                assert m is None
