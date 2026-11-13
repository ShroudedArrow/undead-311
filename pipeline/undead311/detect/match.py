"""Location matching (REQ-DET-MATCH, ZD "Matching (three modes, in this order)").

`match(a, b, p)` returns the match mode and distance, or None:

1. Segment: both snapped, the SAME segment, at most MAX_SEGMENT_DIST apart. Same segment but farther: never a match.
2. Intersection: both snapped, DIFFERENT segments, both within INTERSECTION_M of the same intersection. The recorded
   distance is the sum of the two distances to that intersection (the smallest such sum).
3. Radius: only when at least one of the two is not snapped, and at most RADIUS_M apart. Two snapped cases on
   different segments never match by radius.

With `p.matching == "radius"` (sensitivity grid) segments and intersections are ignored and every pair uses RADIUS_M.
A case is snapped when it has a `segment_id` and `segment_snap_m <= SEGMENT_SNAP_M` (REQ-ING-SNAP.1).
"""

from __future__ import annotations

import math

from undead311.detect.model import Case, Match
from undead311.detect.params import DEFAULT, Params

EARTH_RADIUS_M = 6_371_008.8


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters; symmetric, non-negative, zero for identical points (REQ-DET-MATCH.4)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def case_distance_m(a: Case, b: Case) -> float:
    return distance_m(a.lat, a.lon, b.lat, b.lon)


def is_snapped(c: Case, p: Params = DEFAULT) -> bool:
    return c.segment_id is not None and c.segment_snap_m is not None and c.segment_snap_m <= p.SEGMENT_SNAP_M


def _shared_intersection(a: Case, b: Case, p: Params) -> float | None:
    """Smallest sum of distances to an intersection both cases are within INTERSECTION_M of, else None."""
    bn = dict(b.near_nodes)
    best = None
    for node, da in a.near_nodes:
        db = bn.get(node)
        if db is not None and da <= p.INTERSECTION_M and db <= p.INTERSECTION_M:
            total = da + db
            if best is None or total < best:
                best = total
    return best


def match(a: Case, b: Case, p: Params = DEFAULT) -> Match | None:
    """The one location rule used by incidents, re-reports and mirrors (REQ-DET-MATCH.1-3, .5)."""
    d = case_distance_m(a, b)
    if p.matching == "radius":
        return Match("radius", d) if d <= p.RADIUS_M else None
    if is_snapped(a, p) and is_snapped(b, p):
        if a.segment_id == b.segment_id:
            return Match("segment", d) if d <= p.MAX_SEGMENT_DIST else None
        via = _shared_intersection(a, b, p)
        return Match("intersection", via) if via is not None else None
    return Match("radius", d) if d <= p.RADIUS_M else None


_RANK = {"segment": 0, "intersection": 1, "radius": 2}


def better(a: Match, b: Match) -> Match:
    """The preferred of two matches: segment over intersection over radius, then the shorter distance."""
    return a if (_RANK[a.mode], a.distance_m) <= (_RANK[b.mode], b.distance_m) else b
