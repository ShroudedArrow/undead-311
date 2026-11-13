"""Detection parameters (REQ-DET-PARAM). The only source of truth is `.kiro/steering/zombie-definition.md`.

Defaults are tested against that file (`test_params.py`); overrides go through an explicit `dataclasses.replace`
argument (the sensitivity grid), never environment variables (REQ-DET-PARAM.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from undead311.ingest.closure_flags import MIRROR_WINDOW_HOURS


@dataclass(frozen=True)
class Params:
    """REQ-DET-PARAM.1. `matching` is the grid dimension: 'segment' (three-mode rule) or 'radius' (REQ-DET-MATCH.5)."""

    SEGMENT_SNAP_M: float = 15
    MAX_SEGMENT_DIST: float = 75
    INTERSECTION_M: float = 15
    RADIUS_M: float = 30
    WINDOW_DAYS: float = 60
    INCIDENT_MAX_SPAN_DAYS: float = 7
    BULK_MIN_CASES: int = 50
    BULK_RATIO: float = 10
    MIRROR_WINDOW_HOURS: float = MIRROR_WINDOW_HOURS
    matching: Literal["segment", "radius"] = "segment"

    @property
    def max_match_dist_m(self) -> float:
        """Largest distance at which any rule can match; sizes the grid cell (REQ-DET-MATCH.4)."""
        if self.matching == "radius":
            return self.RADIUS_M
        return max(self.RADIUS_M, self.MAX_SEGMENT_DIST, 2 * self.INTERSECTION_M)


DEFAULT = Params()

#: Names compared with zombie-definition.md by the unit test.
DEFINITION_NAMES = (
    "SEGMENT_SNAP_M",
    "MAX_SEGMENT_DIST",
    "INTERSECTION_M",
    "RADIUS_M",
    "WINDOW_DAYS",
    "INCIDENT_MAX_SPAN_DAYS",
    "BULK_MIN_CASES",
    "BULK_RATIO",
    "MIRROR_WINDOW_HOURS",
)
