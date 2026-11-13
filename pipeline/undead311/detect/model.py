"""Data models for the detector (design.md "Data models").

`Case` is a normalized case after crosswalk and cleaning. Times are timezone-aware UTC. Only a case with a close time
at or after its open time and status Closed counts as closed (`is_closed`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_US = timedelta(microseconds=1)

Tier = Literal["headline", "source_unknown", "sensitivity"]
MatchMode = Literal["segment", "intersection", "radius"]


def to_us(dt: datetime) -> int:
    """Exact integer microseconds since the epoch (UTC); SQL uses epoch_us on the same instants."""
    return (dt - EPOCH) // _US


@dataclass(frozen=True)
class Case:
    id: str
    system: Literal["legacy", "new"]
    open_utc: datetime
    close_utc: datetime | None = None
    type_raw: str = ""
    type_family: str = ""
    scope_tier: Literal["core", "sensitivity"] = "core"
    city_originated_type: bool = False
    catch_all: bool = False
    predecessor_ids: tuple[str, ...] = ()
    source: str | None = None
    closure_text: str | None = None
    closure_code: str | None = None
    coroner_label: str | None = None
    status: str | None = None
    lat: float = 0.0
    lon: float = 0.0
    segment_id: str | None = None
    segment_snap_m: float | None = None
    #: intersections within INTERSECTION_M of this case: (node id, distance in m). Empty without segment geometry.
    near_nodes: tuple[tuple[str, float], ...] = ()
    department: str | None = None
    neighborhood: str | None = None
    district: str | None = None
    street: str | None = None
    bulk_closure: bool = False

    @property
    def is_closed(self) -> bool:
        return self.close_utc is not None and self.close_utc >= self.open_utc

    @property
    def open_us(self) -> int:
        return to_us(self.open_utc)

    @property
    def close_us(self) -> int | None:
        return to_us(self.close_utc) if self.is_closed else None


@dataclass(frozen=True)
class Match:
    mode: MatchMode
    distance_m: float


@dataclass(frozen=True)
class Incident:
    incident_id: str
    member_ids: tuple[str, ...]
    type_family: str
    close_utc: datetime
    coroner_label: str
    department: str | None
    neighborhood: str | None
    district: str | None
    segment_id: str | None
    bulk_closure: bool
    has_transferred_member: bool
    tier: Literal["core", "sensitivity"]


@dataclass(frozen=True)
class Zombie:
    incident_id: str
    member_ids: tuple[str, ...]
    resurrection_id: str
    reports_after: int
    gap_days: float
    match_mode: MatchMode
    distance_m: float
    tier: Tier
    after_temporary_fix: bool
    source_unknown: bool
    chain_id: str
    times_risen: int
    type_family: str
    coroner_label: str
    bulk_closure: bool
    close_year: int
    department: str | None = None
    neighborhood: str | None = None
    district: str | None = None
    segment_id: str | None = None
    baseline_p: float | None = None
    confidence: float = 0.5
    confidence_partial: bool = True
    skeptic_verdict: Literal["survives", "weakened", "explained_away", "not_reviewed"] = "not_reviewed"
    skeptic_notes: str = ""
    is_planned_followup: bool = False

    @property
    def zombie_id(self) -> str:
        return f"{self.incident_id}:{self.resurrection_id}"


@dataclass(frozen=True)
class PlannedFollowup:
    incident_id: str
    resurrection_id: str


@dataclass(frozen=True)
class SeparateDeath:
    incident_id: str
    label: Literal["invalid", "duplicate"]
    rereport_id: str
    type_family: str
    department: str | None


@dataclass(frozen=True)
class Chain:
    chain_id: str
    incident_ids: tuple[str, ...]
    times_risen: int
    headline_count: int

    @property
    def repeat_offender(self) -> bool:
        return self.headline_count >= 3


@dataclass
class DetectionResult:
    incidents: list[Incident] = field(default_factory=list)
    zombies: list[Zombie] = field(default_factory=list)
    planned_followups: list[PlannedFollowup] = field(default_factory=list)
    separate_deaths: list[SeparateDeath] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)
    excluded_pairs: dict[str, int] = field(default_factory=dict)
    #: re-report id -> incident id for every attached R (property tests)
    attribution: dict[str, str] = field(default_factory=dict)
    mirror_ids: frozenset[str] = frozenset()

    @property
    def repeat_offenders(self) -> list[Chain]:
        return [c for c in self.chains if c.repeat_offender]

    def count(self, tier: Tier) -> int:
        return sum(1 for z in self.zombies if z.tier == tier)

    @property
    def headline_count(self) -> int:
        return self.count("headline")
