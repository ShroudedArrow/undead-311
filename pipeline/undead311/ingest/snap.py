"""Snap cases to Boston Street Segments (SAM) and derive intersections (REQ-ING-SNAP.1-6).

* `load_segments` reads the SAM GeoJSON (LineStrings in WGS84).
* `build_intersections`: an intersection is a segment endpoint (first or last vertex), matched at 6 decimal places of
  latitude and longitude and at the same z-level (`F_ZLEV` for the first vertex, `T_ZLEV` for the last), shared by two or
  more distinct segments. SAM has no node IDs. An endpoint used by one segment is a dead end, not an intersection.
* `snap_cases` stores `segment_id`, `segment_snap_m` and `near_nodes` (`node:distance;...`, the intersections within
  INTERSECTION_M of a snapped case) on `cases_clean`. A case is "snapped" only when `segment_snap_m <= SEGMENT_SNAP_M`
  (`detect.match.is_snapped`). Rows that already carry a `segment_id` (the test town) are left as they are, and so is
  `near_nodes` for them (REQ-ING-SNAP.3, .5). Without the segments file nothing is snapped (REQ-ING-SNAP.2).

Known limitation (REQ-ING-SNAP.6, stated in METHODS.md): a shared endpoint is a segment break, and not every break is a
cross street, so the intersection rule can also join two cases on consecutive segments of one street.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point

from undead311.detect.match import distance_m
from undead311.detect.params import DEFAULT, Params

SEGMENTS_FILE = "street_segments_sam.geojson"
SEARCH_M = 100.0  # nearest segments farther than this are not recorded: far beyond SEGMENT_SNAP_M
M_PER_DEG_LAT = 111_320.0
LAT0 = 42.33  # projection origin for metre distances; the error over Boston is below 0.2% of a distance
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT0))
COORD_DECIMALS = 6


@dataclass(frozen=True)
class Segment:
    segment_id: str
    coords: tuple[tuple[float, float], ...]  # (lon, lat)
    f_zlev: int
    t_zlev: int


@dataclass
class Intersections:
    """Endpoints keyed by `node_id`; `nodes` holds only shared endpoints (two or more distinct segments)."""

    nodes: dict[str, tuple[float, float, int]] = field(default_factory=dict)  # node_id -> (lat, lon, zlev)
    segments_at: dict[str, frozenset[str]] = field(default_factory=dict)
    distinct_endpoints: int = 0
    dead_ends: int = 0

    @property
    def dead_end_share(self) -> float:
        return self.dead_ends / self.distinct_endpoints if self.distinct_endpoints else 0.0


@dataclass
class SnapReport:
    available: bool = False
    candidates: int = 0  # in-scope cases that needed snapping
    snapped: int = 0
    unsnapped: int = 0
    pre_snapped: int = 0
    near_node_cases: int = 0
    intersections: int = 0


def node_id(lat: float, lon: float, zlev: int) -> str:
    """Stable ID for an endpoint at 6 decimal places and a z-level; contains no ':' or ';' (see `detect.cases._nodes`)."""
    return f"n{round(lat, COORD_DECIMALS):.6f}_{round(lon, COORD_DECIMALS):.6f}_{int(zlev)}"


def load_segments(path: Path) -> list[Segment]:
    """Segments from the SAM GeoJSON, sorted by ID. A missing z-level counts as 0 (ground level)."""
    out = []
    for f in json.loads(Path(path).read_text())["features"]:
        geom, props = f.get("geometry") or {}, f.get("properties") or {}
        lines = [geom["coordinates"]] if geom.get("type") == "LineString" else (
            geom["coordinates"] if geom.get("type") == "MultiLineString" else [])  # fmt: skip
        coords = [tuple(c[:2]) for line in lines for c in line]
        sid = props.get("SEGMENT_ID", props.get("OBJECTID"))
        if len(coords) < 2 or sid is None:
            continue
        out.append(Segment(str(sid), tuple(coords), int(props.get("F_ZLEV") or 0), int(props.get("T_ZLEV") or 0)))
    return sorted(out, key=lambda s: s.segment_id)


def build_intersections(segments: list[Segment]) -> Intersections:
    """Shared endpoints of two or more distinct segments (REQ-ING-SNAP.4)."""
    seen: dict[str, set[str]] = defaultdict(set)
    where: dict[str, tuple[float, float, int]] = {}
    for s in segments:
        for (lon, lat), z in ((s.coords[0], s.f_zlev), (s.coords[-1], s.t_zlev)):
            nid = node_id(lat, lon, z)
            seen[nid].add(s.segment_id)
            where.setdefault(nid, (round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS), z))
    shared = {n for n, ids in seen.items() if len(ids) >= 2}
    return Intersections(
        nodes={n: where[n] for n in sorted(shared)},
        segments_at={n: frozenset(seen[n]) for n in sorted(shared)},
        distinct_endpoints=len(seen),
        dead_ends=len(seen) - len(shared),
    )


def _xy(lon: float, lat: float) -> tuple[float, float]:
    return (lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT)


def _nearest(tree: STRtree, ids: list[str], xs: np.ndarray, ys: np.ndarray) -> list[tuple[str, float] | None]:
    """Nearest segment and distance in metres per point; ties go to the smallest segment ID (deterministic)."""
    pts = [Point(x, y) for x, y in zip(xs, ys, strict=True)]
    pairs, dist = tree.query_nearest(pts, max_distance=SEARCH_M, return_distance=True, all_matches=True)
    best: dict[int, tuple[float, str]] = {}
    for pi, gi, d in zip(pairs[0], pairs[1], dist, strict=True):
        cand = (round(float(d), 9), ids[int(gi)])
        if int(pi) not in best or cand < best[int(pi)]:
            best[int(pi)] = cand
    return [(best[i][1], best[i][0]) if i in best else None for i in range(len(pts))]


def snap_cases(
    con: duckdb.DuckDBPyConnection,
    segments_path: Path | None,
    p: Params = DEFAULT,
    table: str = "cases_clean",
) -> SnapReport:
    """Fill `segment_id`, `segment_snap_m` and `near_nodes` on `table` (REQ-ING-SNAP.1-5); also creates `intersections`."""
    report = SnapReport()
    con.execute(f"alter table {table} add column if not exists near_nodes varchar")
    con.execute("drop table if exists intersections")
    con.execute("create table intersections(node_id varchar, lat double, lon double, zlev integer, n_segments integer)")
    report.pre_snapped = con.execute(
        f"select count(*) from {table} where segment_id is not null and scope_tier in ('core','sensitivity')"
    ).fetchone()[0]
    if segments_path is None or not Path(segments_path).is_file():
        return report  # REQ-ING-SNAP.2: radius matching only; the caller records `segments: missing`
    segs = load_segments(segments_path)
    if not segs:
        return report
    report.available = True
    inter = build_intersections(segs)
    report.intersections = len(inter.nodes)
    if inter.nodes:
        con.executemany(
            "insert into intersections values (?,?,?,?,?)",
            [(n, la, lo, z, len(inter.segments_at[n])) for n, (la, lo, z) in inter.nodes.items()],
        )
    rows = con.execute(
        f"select id, system, lat, lon from {table} where segment_id is null and scope_tier in ('core','sensitivity') "
        "and lat is not null and lon is not null order by id, system"
    ).fetchall()
    report.candidates = len(rows)
    if not rows:
        return report
    lines = [LineString([_xy(lo, la) for lo, la in s.coords]) for s in segs]
    seg_tree = STRtree(lines)
    ids = [s.segment_id for s in segs]
    xs = np.array([_xy(r[3], r[2])[0] for r in rows])
    ys = np.array([_xy(r[3], r[2])[1] for r in rows])
    nearest = _nearest(seg_tree, ids, xs, ys)
    node_ids = list(inter.nodes)
    node_tree = STRtree([Point(_xy(lo, la)) for la, lo, _ in inter.nodes.values()]) if node_ids else None
    near: dict[int, list[tuple[str, float]]] = defaultdict(list)
    if node_tree is not None:
        pts = [Point(x, y) for x, y in zip(xs, ys, strict=True)]
        pi, ni = node_tree.query(pts, predicate="dwithin", distance=p.INTERSECTION_M + 1.0)
        for i, j in zip(pi, ni, strict=True):
            la, lo, _ = inter.nodes[node_ids[int(j)]]
            d = distance_m(rows[int(i)][2], rows[int(i)][3], la, lo)
            if d <= p.INTERSECTION_M:
                near[int(i)].append((node_ids[int(j)], round(d, 3)))
    con.execute("drop table if exists snap_result")
    con.execute("create temp table snap_result(id varchar, system varchar, seg varchar, snap double, near varchar)")
    out = []
    for i, (cid, system, _la, _lo) in enumerate(rows):
        hit = nearest[i]
        snapped = hit is not None and hit[1] <= p.SEGMENT_SNAP_M
        nn = ";".join(f"{n}:{d}" for n, d in sorted(near[i])) if snapped and near.get(i) else None
        out.append((cid, system, hit[0] if hit else None, round(hit[1], 3) if hit else None, nn))
        report.snapped += bool(snapped)
        report.near_node_cases += bool(nn)
    report.unsnapped = report.candidates - report.snapped
    con.executemany("insert into snap_result values (?,?,?,?,?)", out)
    con.execute(f"""
        update {table} t set segment_id = r.seg, segment_snap_m = r.snap, near_nodes = r.near
        from snap_result r where t.id = r.id and t.system = r.system and t.segment_id is null
    """)
    con.execute("drop table snap_result")
    return report
