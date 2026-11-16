"""REQ-ING-SNAP.1-6: snapping, intersections and near_node_ids on small hand-built segment grids and the real SAM file."""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path

import duckdb
import pytest

from undead311.detect.cases import cases_from_table
from undead311.detect.match import distance_m, match
from undead311.detect.params import DEFAULT
from undead311.ingest.snap import SEGMENTS_FILE, build_intersections, load_segments, node_id, snap_cases

LAT0, LON0 = 42.3300, -71.0800
M_LAT = 111_320.0
M_LON = M_LAT * math.cos(math.radians(LAT0))


def at(east_m: float, north_m: float) -> tuple[float, float]:
    """(lon, lat) of a point `east_m`, `north_m` metres from the grid origin."""
    return (LON0 + east_m / M_LON, LAT0 + north_m / M_LAT)


def feature(sid, pts, f=0, t=0):
    return {"type": "Feature", "properties": {"SEGMENT_ID": sid, "F_ZLEV": f, "T_ZLEV": t},
            "geometry": {"type": "LineString", "coordinates": [list(at(*p)) for p in pts]}}  # fmt: skip


def write_grid(path: Path, features) -> Path:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def crossing(path: Path) -> Path:
    """Two streets crossing at the origin, each split in two: four segments meeting at one node, 4 dead ends."""
    return write_grid(path, [
        feature(1, [(-200, 0), (0, 0)]), feature(2, [(0, 0), (200, 0)]),
        feature(3, [(0, -200), (0, 0)]), feature(4, [(0, 0), (0, 200)]),
    ])  # fmt: skip


def cases_table(points: list[tuple[str, float, float]], pre: dict | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, lat double, lon double, scope_tier varchar, "
                "segment_id varchar, segment_snap_m double, open_time_utc timestamp, type_family varchar)")  # fmt: skip
    for cid, east, north in points:
        lon, lat = at(east, north)
        seg, snap = (pre or {}).get(cid, (None, None))
        con.execute("insert into cases_clean values (?,?,?,?,?,?,?,'2024-01-01','pothole_roadway')",
                    [cid, "legacy", lat, lon, "core", seg, snap])
    return con


def row(con, cid):
    return con.execute("select segment_id, segment_snap_m, near_nodes from cases_clean where id = ?", [cid]).fetchone()


def test_req_ing_snap_4_four_segments_meeting_make_one_intersection_and_four_dead_ends(tmp_path):
    inter = build_intersections(load_segments(crossing(tmp_path / "g.geojson")))
    assert len(inter.nodes) == 1 and inter.dead_ends == 4 and inter.distinct_endpoints == 5
    assert abs(inter.dead_end_share - 0.8) < 1e-9


def test_req_ing_snap_4_endpoints_match_at_six_decimals_and_the_same_z_level(tmp_path):
    a = [feature(1, [(-100, 0), (0, 0)], 0, 0), feature(2, [(0, 0), (100, 0)], 0, 0)]
    assert len(build_intersections(load_segments(write_grid(tmp_path / "a.geojson", a))).nodes) == 1
    over = [feature(1, [(-100, 0), (0, 0)], 0, 1), feature(2, [(0, 0), (100, 0)], 0, 0)]  # overpass: z-levels differ
    assert not build_intersections(load_segments(write_grid(tmp_path / "o.geojson", over))).nodes
    # 1e-7 degrees apart rounds to the same 6-decimal point; 1e-5 degrees apart does not
    assert node_id(42.3300001, -71.08, 0) == node_id(42.33, -71.08, 0)
    assert node_id(42.33001, -71.08, 0) != node_id(42.33, -71.08, 0)


def test_req_ing_snap_4_a_segment_with_both_ends_at_one_point_is_not_an_intersection(tmp_path):
    loop = write_grid(tmp_path / "l.geojson", [feature(1, [(0, 0), (50, 50), (0, 50), (0, 0)])])
    assert not build_intersections(load_segments(loop)).nodes


def test_req_ing_snap_1_a_case_snaps_only_within_15_m_and_stores_both_columns(tmp_path):
    con = cases_table([("near", 100, 10), ("edge", 100, 14.5), ("far", 100, 40), ("lost", 100, 500)])
    rep = snap_cases(con, crossing(tmp_path / "g.geojson"))
    assert rep.available and rep.candidates == 4 and rep.snapped == 2 and rep.unsnapped == 2
    assert row(con, "near")[0] == "2" and abs(row(con, "near")[1] - 10) < 0.1
    assert row(con, "edge")[0] == "2"
    far = row(con, "far")
    assert far[0] == "2" and far[1] > DEFAULT.SEGMENT_SNAP_M  # stored, but not snapped
    assert row(con, "lost")[:2] == (None, None)  # nothing within the search cap


def test_req_ing_snap_1_the_loader_treats_only_snapped_cases_as_snapped(tmp_path):
    from undead311.detect.match import is_snapped

    con = cases_table([("near", 100, 10), ("far", 100, 40)])
    snap_cases(con, crossing(tmp_path / "g.geojson"))
    by = {c.id: c for c in cases_from_table(con) if True}
    assert is_snapped(by["near"]) and not is_snapped(by["far"])


def test_req_ing_snap_4_near_nodes_hold_the_intersections_within_15_m_with_their_distance(tmp_path):
    """Cases 14 m and 16 m from the crossing, on different segments: only the 14 m case has the node."""
    con = cases_table([("in", 14, 0), ("out", 0, -16), ("mid", 100, 5)])
    snap_cases(con, crossing(tmp_path / "g.geojson"))
    node = next(iter(build_intersections(load_segments(tmp_path / "g.geojson")).nodes))
    near = row(con, "in")[2]
    assert near is not None and near.startswith(node + ":") and abs(float(near.split(":")[1]) - 14) < 0.2
    assert row(con, "out")[2] is None and row(con, "mid")[2] is None


def test_req_det_match_2_snapped_cases_on_different_segments_match_via_the_derived_intersection(tmp_path):
    """End to end: derived near_nodes make the three-mode rule match across the crossing and nowhere else."""
    con = cases_table([("a", -10, 0), ("b", 0, 10), ("c", -10, 20)])
    snap_cases(con, crossing(tmp_path / "g.geojson"))
    by = {c.id: c for c in cases_from_table(con)}
    m = match(by["a"], by["b"])
    assert m is not None and m.mode == "intersection" and abs(m.distance_m - 20) < 0.5
    assert match(by["a"], by["c"]) is None  # c is on another segment and 20 m from the node


def test_req_ing_snap_3_pre_snapped_rows_are_left_alone(tmp_path):
    con = cases_table([("fixture", 100, 10), ("plain", 100, 10)], pre={"fixture": ("TOWN-1", 3.0)})
    rep = snap_cases(con, crossing(tmp_path / "g.geojson"))
    assert row(con, "fixture") == ("TOWN-1", 3.0, None) and rep.pre_snapped == 1 and rep.candidates == 1
    assert row(con, "plain")[0] == "2"


def test_req_ing_snap_5_pre_snapped_rows_keep_near_nodes_empty_even_beside_an_intersection(tmp_path):
    """REQ-ING-SNAP.5: a pre-snapped fixture row at the crossing gets no near_nodes, so intersection mode never applies to it."""
    con = cases_table([("fixture", 0, 0), ("plain", 0, 0)], pre={"fixture": ("TOWN-1", 3.0)})
    snap_cases(con, crossing(tmp_path / "g.geojson"))
    assert not row(con, "fixture")[2]
    assert row(con, "plain")[2]  # a row that is snapped here does get the crossing


def test_req_ing_snap_6_methods_page_states_the_segment_break_limitation():
    """REQ-ING-SNAP.6: docs/METHODS.md says a shared endpoint is a segment break, not always a cross street, and that dead ends are not intersections."""
    text = (Path(__file__).resolve().parents[3] / "docs" / "METHODS.md").read_text()
    assert "segment break" in text and "not every break is a cross street" in text
    assert "mid-block" in text and "dead end" in text


def test_req_ing_snap_2_without_the_file_nothing_is_snapped(tmp_path):
    con = cases_table([("a", 0, 5)])
    rep = snap_cases(con, tmp_path / "missing.geojson")
    assert not rep.available and rep.snapped == 0 and row(con, "a") == (None, None, None)
    assert snap_cases(cases_table([("a", 0, 5)]), None).available is False


def test_req_ing_snap_1_nearest_tie_goes_to_the_smallest_segment_id(tmp_path):
    """A case exactly at the shared endpoint is equally near segments 1 to 4; the result is the smallest ID."""
    con = cases_table([("x", 0, 0)])
    snap_cases(con, crossing(tmp_path / "g.geojson"))
    assert row(con, "x")[0] == "1"


def test_req_ing_snap_1_snapping_is_invariant_to_row_order(tmp_path):
    pts = [("a", 50, 3), ("b", -30, 8), ("c", 5, 90), ("d", 4, -12)]
    out = []
    for order in (pts, list(reversed(pts))):
        con = cases_table(order)
        snap_cases(con, crossing(tmp_path / "g.geojson"))
        out.append(sorted(con.execute("select id, segment_id, segment_snap_m, near_nodes from cases_clean").fetchall()))
    assert out[0] == out[1]


# --- the real SAM file (downloaded by `make data-download`); skipped when it is not there --------------------------------


def sam_file() -> Path | None:
    for base in (os.environ.get("DATA_DIR"), str(Path(__file__).resolve().parents[3] / ".local-data" / "data")):
        if base and (Path(base) / "raw" / SEGMENTS_FILE).is_file():
            return Path(base) / "raw" / SEGMENTS_FILE
    return None


@pytest.mark.slow
@pytest.mark.skipif(sam_file() is None, reason="street_segments_sam.geojson not downloaded (make data-download)")
def test_req_ing_snap_4_intersection_count_matches_the_downloaded_file():
    """REQ-ING-SNAP.4/.6: recount the shared endpoints straight from the raw GeoJSON, independently of `snap.py`."""
    path = sam_file()
    feats = json.loads(path.read_text())["features"]
    ends: dict[tuple, set] = defaultdict(set)
    for f in feats:
        c, pr = f["geometry"]["coordinates"], f["properties"]
        for (x, y), z in ((c[0], pr["F_ZLEV"]), (c[-1], pr["T_ZLEV"])):
            ends[(round(y, 6), round(x, 6), z)].add(pr["SEGMENT_ID"])
    expected = sum(len(v) >= 2 for v in ends.values())
    inter = build_intersections(load_segments(path))
    assert len(inter.nodes) == expected > 5000
    assert inter.distinct_endpoints == len(ends)
    assert 0.05 < inter.dead_end_share < 0.30  # METHODS.md quotes about 15%
    print(f"SAM: {len(feats)} segments, {len(inter.nodes)} intersections, {inter.dead_end_share:.1%} dead ends")


@pytest.mark.slow
@pytest.mark.skipif(sam_file() is None, reason="street_segments_sam.geojson not downloaded (make data-download)")
def test_req_ing_snap_1_points_on_real_segments_snap_to_them_and_distant_points_do_not():
    path = sam_file()
    segs = load_segments(path)[:300]
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, lat double, lon double, scope_tier varchar, "
                "segment_id varchar, segment_snap_m double, open_time_utc timestamp, type_family varchar)")  # fmt: skip
    for s in segs:
        (lon0, lat0), (lon1, lat1) = s.coords[0], s.coords[-1]
        con.execute("insert into cases_clean values (?,?,?,?,?,?,?,NULL,NULL)",
                    [f"m{s.segment_id}", "legacy", (lat0 + lat1) / 2, (lon0 + lon1) / 2, "core", None, None])  # fmt: skip
    snap_cases(con, path)
    got = dict(con.execute("select id, segment_snap_m from cases_clean").fetchall())
    # a segment's chord midpoint is within 15 m of its own line unless the segment bends strongly
    assert sum(v is not None and v <= 15 for v in got.values()) > 0.9 * len(segs)
    assert distance_m(42.33, -71.08, 42.34, -71.08) > 1000  # sanity of the helper used above


def bridge(path: Path) -> Path:
    """A ground street (id 10) under a bridge (id 20, z-level 1 at both ends), 6 m apart in plan view."""
    return write_grid(path, [
        feature(10, [(-200, 0), (200, 0)], 0, 0), feature(20, [(-200, 6), (200, 6)], 1, 1),
        feature(30, [(200, 0), (400, 0)], 0, 0),
    ])  # fmt: skip


def test_req_ing_snap_1_a_case_under_a_bridge_snaps_to_the_ground_street_not_the_road_above(tmp_path):
    """ops#83: the elevated segment is nearer (1 m vs 5 m) but the ground segment is within SEGMENT_SNAP_M, so it wins."""
    con = cases_table([("under", 0, 5), ("under2", 50, 5), ("far", 0, 25)])
    rep = snap_cases(con, bridge(tmp_path / "b.geojson"))
    assert row(con, "under")[0] == "10" and row(con, "under2")[0] == "10"
    assert rep.z_preferred == 2 and rep.snapped == 2
    assert row(con, "far")[0] == "20" and row(con, "far")[1] > DEFAULT.SEGMENT_SNAP_M  # nothing on the ground within 15 m
    by = {c.id: c for c in cases_from_table(con)}
    assert match(by["under"], by["under2"]) is not None  # same ground segment, 50 m apart


def test_req_ing_snap_1_an_elevated_segment_is_used_when_no_ground_segment_is_within_snap_distance(tmp_path):
    con = cases_table([("ramp", 0, 7)])
    only_ramp = write_grid(tmp_path / "r.geojson", [feature(20, [(-200, 0), (200, 0)], 1, 1)])
    rep = snap_cases(con, only_ramp)
    assert row(con, "ramp")[0] == "20" and rep.snapped == 1 and rep.z_preferred == 0
