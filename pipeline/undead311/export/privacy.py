"""Block-level privacy for repeat offenders (REQ-EXP-PRIV.1; product.md "Privacy in display").

A repeat-offender chain driven by resident reports (more than half of its re-reports are not city-originated) on a
residential or unknown-class street is exported at block level, so the map never singles out a home:

* the chain's segment is known and its midpoint is available: the segment midpoint (half the line's length along it,
  measured in metres in the snapping projection; a multi-part segment is walked part by part, with no made-up connector);
* otherwise (unsnapped, or no segment geometry at hand): the center of a `GRID_CELL_M` (100 m) grid cell.

The chain's location is used for EVERY exported row that touches the chain (repeat_offenders, points, cards), so a join on
`chain_id` or case ID cannot recover the exact point; the street text of those cards is dropped too (ops#167). A re-report
of the chain that starts a chain of its own is covered too (`block_location_by_case`, ops#180).
Every other chain keeps the exact case point. The safe direction is the default: a chain is shown exactly only when its
street class is KNOWN not to be residential and the chain is not resident-driven, or when it is city-driven. A new-system
re-report has no origin field, so it counts as resident (not city-originated).

The class comes from the first of `CLASS_KEYS` that the SAM segment carries. The raw SAM file was not available when this was
written, so the real field name is unconfirmed; with none of the keys present every class is unknown and every
resident-driven chain is block-level (`docs/METHODS.md`).
"""

from __future__ import annotations

import itertools
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from undead311.detect.core import is_city_originated
from undead311.detect.model import Case, DetectionResult
from undead311.ingest.snap import M_PER_DEG_LAT, M_PER_DEG_LON

GRID_CELL_M = 100.0  # REQ-EXP-PRIV.1
CLASS_KEYS = ("ST_CLASS", "STREET_CLASS", "ROAD_CLASS", "ROADCLASS", "FUNC_CLASS", "FUNCCLASS", "CLASS")
#: words that mark a street as NOT residential; anything else (including no class) is residential or unknown
NON_RESIDENTIAL_WORDS = (
    "arterial", "collector", "highway", "freeway", "expressway", "interstate", "ramp", "parkway", "bridge",
    "major", "principal", "primary", "commercial", "industrial",
)  # fmt: skip
StreetKind = Literal["residential", "non_residential", "unknown"]


@dataclass(frozen=True)
class SegmentInfo:
    """What the export needs of one SAM segment: its midpoint (lat, lon) and its raw class text, if any."""

    midpoint: tuple[float, float]
    street_class: str | None = None


def street_kind(raw: str | None) -> StreetKind:
    """`unknown` for no class text, `non_residential` for a clearly busier class, `residential` otherwise (local etc.)."""
    text = (raw or "").strip().lower()
    if not text:
        return "unknown"
    if any(w in text for w in NON_RESIDENTIAL_WORDS):
        return "non_residential"
    return "residential"


def segment_midpoint(parts: Sequence[Sequence[Sequence[float]]]) -> tuple[float, float] | None:
    """(lat, lon) half the segment's length along it (REQ-EXP-PRIV.1, ops#169).

    Lengths are metres in the snapping projection (`M_PER_DEG_LON` east, `M_PER_DEG_LAT` north), not degrees, so a bent
    line is not pulled off its half-way point. Several parts are walked in order and only their own lengths count: no
    connector is invented between them, so the point is always on the street. None for fewer than two distinct points."""
    lines = [[(c[0] * M_PER_DEG_LON, c[1] * M_PER_DEG_LAT) for c in part] for part in parts if len(part) >= 2]
    lengths = [[math.dist(a, b) for a, b in itertools.pairwise(line)] for line in lines]
    total = sum(sum(ls) for ls in lengths)
    if total <= 0:
        return None
    left = total / 2
    for line, ls in zip(lines, lengths, strict=True):
        for (a, b), n in zip(itertools.pairwise(line), ls, strict=True):
            if n > 0 and left <= n:
                f = left / n
                x, y = a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
                return round(y / M_PER_DEG_LAT, 6), round(x / M_PER_DEG_LON, 6)
            left -= n
    x, y = lines[-1][-1]  # float rounding only: the end of the last part
    return round(y / M_PER_DEG_LAT, 6), round(x / M_PER_DEG_LON, 6)


def load_segment_info(path: Path) -> dict[str, SegmentInfo]:
    """Midpoint and class text per SAM segment ID; `{}` when the file is missing."""
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, SegmentInfo] = {}
    for f in json.loads(p.read_text()).get("features", []):
        geom, props = f.get("geometry") or {}, f.get("properties") or {}
        parts = [geom["coordinates"]] if geom.get("type") == "LineString" else (
            geom["coordinates"] if geom.get("type") == "MultiLineString" else [])  # fmt: skip
        sid = props.get("SEGMENT_ID", props.get("OBJECTID"))
        mid = segment_midpoint(parts) if sid is not None else None
        if mid is None:
            continue
        upper = {str(k).upper(): v for k, v in props.items()}
        cls = next((str(upper[k]) for k in CLASS_KEYS if upper.get(k) not in (None, "")), None)
        out[str(sid)] = SegmentInfo(mid, cls)
    return out


def grid_cell_center(lat: float, lon: float, cell_m: float = GRID_CELL_M) -> tuple[float, float]:
    """Center of the `cell_m` grid cell holding the point (the snapping projection, origin at 0 m east and 0 m north)."""
    x, y = lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT
    cx, cy = (math.floor(x / cell_m) + 0.5) * cell_m, (math.floor(y / cell_m) + 0.5) * cell_m
    return round(cy / M_PER_DEG_LAT, 6), round(cx / M_PER_DEG_LON, 6)


def resident_driven(rereport_ids: Iterable[str], cases: Mapping[str, Case]) -> bool:
    """More than half of the chain's re-reports are not city-originated (REQ-EXP-PRIV.1). No re-reports: False."""
    ids = list(rereport_ids)
    resident = sum(not is_city_originated(cases[i]) for i in ids)
    return bool(ids) and 2 * resident > len(ids)


def offender_location(
    point: tuple[float, float],
    segment_id: str | None,
    driven_by_residents: bool,
    segments: Mapping[str, SegmentInfo] | None,
) -> tuple[float, float, bool]:
    """(lat, lon, block_level) for a repeat-offender chain (REQ-EXP-PRIV.1).

    Exact point when the chain is city-driven, or when its street is known not to be residential. Otherwise the segment
    midpoint when it is known, else the 100 m cell center."""
    info = (segments or {}).get(segment_id) if segment_id is not None else None
    if not driven_by_residents or (info is not None and street_kind(info.street_class) == "non_residential"):
        return point[0], point[1], False
    if info is not None:
        return info.midpoint[0], info.midpoint[1], True
    lat, lon = grid_cell_center(*point)
    return lat, lon, True


def chain_rereport_ids(attribution: Mapping[str, str], incident_ids: Iterable[str]) -> list[str]:
    """Every re-report attached to one of the chain's incidents, sorted (ZD step 5: `reports_after` counts every attached
    R, not only the first). Planned follow-ups and city re-reports are included: they are re-reports at the place too
    (REQ-EXP-PRIV.1, ops#168)."""
    wanted = set(incident_ids)
    return sorted(r for r, inc in attribution.items() if inc in wanted)


def block_level_locations(
    result: DetectionResult, cases: Mapping[str, Case], segments: Mapping[str, SegmentInfo] | None
) -> dict[str, tuple[float, float, bool]]:
    """chain_id -> (lat, lon, block_level) for every repeat-offender chain (REQ-EXP-PRIV.1). The location of a chain is its
    first incident's earliest-opened member, coarsened when the chain is resident-driven on a residential or unknown street."""
    by_inc = {i.incident_id: i for i in result.incidents}
    out: dict[str, tuple[float, float, bool]] = {}
    for c in sorted(result.repeat_offenders, key=lambda c: c.chain_id):
        first = by_inc[c.chain_id]
        rep = min((cases[m] for m in first.member_ids), key=lambda x: (x.open_utc, x.id))
        driven = resident_driven(chain_rereport_ids(result.attribution, c.incident_ids), cases)
        out[c.chain_id] = offender_location((rep.lat, rep.lon), first.segment_id, driven, segments)
    return out


def block_location_by_case(
    result: DetectionResult,
    locations: Mapping[str, tuple[float, float, bool]],
) -> dict[str, tuple[float, float]]:
    """case_id -> block (lat, lon) for every case that touches a block-level chain (REQ-EXP-PRIV.1, ops#180).

    A case touches a chain when it is a member of one of the chain's incidents or one of its attached re-reports. A
    re-report that is later closed starts its own chain (a non-first attached re-report, or a planned follow-up), and that
    chain's zombies would otherwise export the exact point of a case the block-level chain counts, so a join on the case ID
    could undo the block location. So the block location spreads over every zombie link: all cases of a zombie (the
    original's members and the re-report) share the location of any block-level case among them, transitively. Where two
    block-level chains meet, the smaller chain ID's location is used. Cases that touch no block-level chain are absent."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_inc = {i.incident_id: i for i in result.incidents}
    seeds: list[tuple[str, str]] = []  # (chain_id, a case of the chain)
    for c in sorted(result.repeat_offenders, key=lambda c: c.chain_id):
        loc = locations.get(c.chain_id)
        if loc is None or not loc[2]:
            continue
        cases = {m for i in c.incident_ids for m in by_inc[i].member_ids}
        cases |= {r for r, inc in result.attribution.items() if inc in set(c.incident_ids)}
        first = min(cases)
        for x in cases:
            union(first, x)
        seeds.append((c.chain_id, first))
    if not seeds:
        return {}
    for z in result.zombies:
        for x in (*z.member_ids, z.resurrection_id):
            union(z.resurrection_id, x)
    where: dict[str, tuple[float, float]] = {}
    for chain_id, case in seeds:  # sorted by chain_id: the smallest chain ID wins a shared component
        loc = locations[chain_id]
        where.setdefault(find(case), (loc[0], loc[1]))
    return {x: where[find(x)] for x in list(parent) if find(x) in where}


__all__ = [
    "CLASS_KEYS", "GRID_CELL_M", "SegmentInfo", "block_level_locations", "block_location_by_case", "chain_rereport_ids", "grid_cell_center",
    "load_segment_info", "offender_location", "resident_driven", "segment_midpoint", "street_kind",
]  # fmt: skip
