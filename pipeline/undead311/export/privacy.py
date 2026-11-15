"""Block-level privacy for repeat offenders (REQ-EXP-PRIV.1; product.md "Privacy in display").

A repeat-offender chain driven by resident reports (more than half of its re-reports are not city-originated) on a
residential or unknown-class street is exported at block level, so the map never singles out a home:

* the chain's segment is known and its midpoint is available: the segment midpoint (half the line's length along it);
* otherwise (unsnapped, or no segment geometry at hand): the center of a `GRID_CELL_M` (100 m) grid cell.

Every other chain keeps the exact case point. The safe direction is the default: a chain is shown exactly only when its
street class is KNOWN not to be residential and the chain is not resident-driven, or when it is city-driven. A new-system
re-report has no origin field, so it counts as resident (not city-originated).

The class comes from the first of `CLASS_KEYS` that the SAM segment carries. The raw SAM file was not available when this was
written, so the real field name is unconfirmed; with none of the keys present every class is unknown and every
resident-driven chain is block-level (`docs/METHODS.md`).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shapely.geometry import LineString

from undead311.detect.core import is_city_originated
from undead311.detect.model import Case, Zombie
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


def load_segment_info(path: Path) -> dict[str, SegmentInfo]:
    """Midpoint and class text per SAM segment ID; `{}` when the file is missing."""
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, SegmentInfo] = {}
    for f in json.loads(p.read_text()).get("features", []):
        geom, props = f.get("geometry") or {}, f.get("properties") or {}
        lines = [geom["coordinates"]] if geom.get("type") == "LineString" else (
            geom["coordinates"] if geom.get("type") == "MultiLineString" else [])  # fmt: skip
        coords = [tuple(c[:2]) for line in lines for c in line]
        sid = props.get("SEGMENT_ID", props.get("OBJECTID"))
        if len(coords) < 2 or sid is None:
            continue
        mid = LineString(coords).interpolate(0.5, normalized=True)
        upper = {str(k).upper(): v for k, v in props.items()}
        cls = next((str(upper[k]) for k in CLASS_KEYS if upper.get(k) not in (None, "")), None)
        out[str(sid)] = SegmentInfo((round(mid.y, 6), round(mid.x, 6)), cls)
    return out


def grid_cell_center(lat: float, lon: float, cell_m: float = GRID_CELL_M) -> tuple[float, float]:
    """Center of the `cell_m` grid cell holding the point (the snapping projection, origin at 0 m east and 0 m north)."""
    x, y = lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT
    cx, cy = (math.floor(x / cell_m) + 0.5) * cell_m, (math.floor(y / cell_m) + 0.5) * cell_m
    return round(cy / M_PER_DEG_LAT, 6), round(cx / M_PER_DEG_LON, 6)


def resident_driven(resurrection_ids: Iterable[str], cases: Mapping[str, Case]) -> bool:
    """More than half of the chain's re-reports are not city-originated (REQ-EXP-PRIV.1). No re-reports: False."""
    ids = list(resurrection_ids)
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


def chain_resurrection_ids(zombies: Iterable[Zombie], chain_id: str) -> list[str]:
    """Every re-report that is a possible zombie in the chain, all tiers, sorted."""
    return sorted(z.resurrection_id for z in zombies if z.chain_id == chain_id)


__all__ = [
    "CLASS_KEYS", "GRID_CELL_M", "SegmentInfo", "chain_resurrection_ids", "grid_cell_center", "load_segment_info",
    "offender_location", "resident_driven", "street_kind",
]  # fmt: skip
