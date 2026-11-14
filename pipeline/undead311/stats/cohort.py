"""Eligible originals and the closed cases under them (glossary, REQ-STAT-SF.1 denominator).

An eligible original is an incident that can be an original under ZD step 3 (no transferred member) and is fully
observed: `close_time + WINDOW_DAYS <= data end`. The cohort for the headline is the core-scope incidents; the
all-tier cohort adds sensitivity-scope incidents (REQ-STAT-TIER.2 keeps the two apart).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta

from undead311.detect.model import Incident
from undead311.detect.params import DEFAULT, Params

#: the meteorological seasons (glossary), by month
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}  # fmt: skip

#: grid cell edge in m for a case without a street segment: 2 x RADIUS_M (glossary "Spot")
CELL_FACTOR = 2
M_PER_DEG = 111_320.0
COS_BOSTON = math.cos(math.radians(42.33))


def eligible_originals(
    incidents: Iterable[Incident], data_end: datetime, params: Params = DEFAULT, *, all_tiers: bool = False
) -> list[Incident]:
    """Incidents that may be originals and are fully observed, sorted by ID (REQ-STAT-SF.1, glossary).

    `all_tiers=False` keeps the headline scope (core incidents); `True` adds sensitivity-scope incidents.
    """
    horizon = timedelta(days=params.WINDOW_DAYS)
    return sorted(
        (
            i
            for i in incidents
            if not i.has_transferred_member
            and (all_tiers or i.tier == "core")
            and i.close_utc + horizon <= data_end
        ),
        key=lambda i: i.incident_id,
    )


def season(when: datetime) -> str:
    """Meteorological season of a UTC timestamp (glossary)."""
    return SEASONS[when.month]


SEASON_INDEX = {"winter": 0, "spring": 1, "summer": 2, "autumn": 3}


def season_idx(when: datetime) -> int:
    """Season index (0 winter, 1 spring, 2 summer, 3 autumn) of a UTC timestamp."""
    return SEASON_INDEX[SEASONS[when.month]]


def spot_key(segment_id: str | None, lat: float, lon: float, params: Params = DEFAULT) -> str:
    """The matching location unit: the segment when snapped, else a 60 m grid cell (glossary "Spot")."""
    if segment_id:
        return f"seg:{segment_id}"
    cell_m = CELL_FACTOR * params.RADIUS_M
    row = math.floor(lat * M_PER_DEG / cell_m)
    col = math.floor(lon * M_PER_DEG * COS_BOSTON / cell_m)  # one fixed latitude, so cells are a regular grid
    return f"cell:{row}:{col}"
