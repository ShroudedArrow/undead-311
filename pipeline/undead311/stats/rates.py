"""Two-number scorecard: closed on time vs stayed fixed (REQ-STAT-SF, REQ-STAT-INT, REQ-STAT-TIER).

Unit of count: a closed in-scope case that belongs to an eligible original (cohort.py). Cases whose `on_time` is
unknown are left out of both rates and counted in `n_closed - n_on_time_known` (REQ-STAT-SF.1).

* on-time rate: on-time cases / cases with a known `on_time`.
* raw stayed-fixed rate: on-time cases whose incident is not a possible zombie in the tier set / the same denominator.
  Planned follow-ups and separate deaths are not zombies, so they count as not resurrected (REQ-STAT-SF.2).
  The numerator is a subset of the on-time cases, so stayed-fixed <= on-time for every group (testing.md #10).

`tier_set` "headline" counts only headline zombies and core-scope incidents; "all" counts zombies of every tier and
adds sensitivity-scope incidents. The headline never includes `source_unknown`, `city_rereport` or `sensitivity` (REQ-STAT-TIER.2).
The adjusted rate (REQ-STAT-SF.3) adds back the expected coincidences among on-time originals that are zombies of the
tier set: `adj_k = raw_k + min(E, Z)`, with `Z` the on-time cases in zombie incidents and `E` the sum of each such
incident's baseline `p` over its on-time cases (an original without a baseline adds nothing). `raw_k + Z` is the on-time
count, so the adjusted rate is at most the on-time rate; `min(adj, on_time)` is applied anyway as the clamp the method
requires. It is null when no baseline is given.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from undead311.detect.model import ZOMBIE_TIERS, Case, DetectionResult, Incident
from undead311.detect.params import DEFAULT, Params
from undead311.stats.cohort import eligible_originals
from undead311.stats.intervals import Rate, make_rate, wilson_p
from undead311.stats.meta import params_json

TierSet = Literal["headline", "all"]
CITYWIDE = "citywide"


@dataclass(frozen=True)
class Scorecard:
    family: str
    tier_set: TierSet
    n_closed: int
    n_on_time_known: int
    on_time: Rate
    stayed_fixed_raw: Rate
    stayed_fixed_adj: Rate | None = None

    def to_json(self) -> dict:
        return {
            "family": self.family, "tier_set": self.tier_set, "n_closed": self.n_closed,
            "n_on_time_known": self.n_on_time_known, "on_time": self.on_time.to_json(),
            "stayed_fixed_raw": self.stayed_fixed_raw.to_json(),
            "stayed_fixed_adj": self.stayed_fixed_adj.to_json() if self.stayed_fixed_adj else None,
        }  # fmt: skip


def zombie_incident_ids(result: DetectionResult, tier_set: TierSet) -> frozenset[str]:
    """Incidents that count as resurrected: headline zombies only, or zombies of every tier (REQ-STAT-SF.2)."""
    return frozenset(z.incident_id for z in result.zombies if tier_set == "all" or z.tier == "headline")


def adjusted_rate(stayed: int, on_time: int, known: int, expected: float) -> Rate | None:
    """Adjusted stayed-fixed rate: `stayed + expected` coincidences added back, clamped to the on-time rate (REQ-STAT-SF.3).

    `expected` is capped at the on-time cases that were resurrected (`on_time - stayed`), so the result lies between the
    raw and the on-time rate. `k` is the rounded effective count; the interval is Wilson around the fractional rate.
    """
    if known <= 0:
        return make_rate(0, 0)
    add = min(max(expected, 0.0), float(on_time - stayed))
    rate = min((stayed + add) / known, on_time / known)  # the clamp: never above the on-time rate
    lo, hi = wilson_p(rate, known)
    return Rate(k=round(rate * known), n=known, rate=rate, lo=lo, hi=hi)


def scorecards(
    result: DetectionResult,
    cases: Mapping[str, Case],
    data_end: datetime,
    params: Params = DEFAULT,
    baseline: Callable[[Incident], float | None] | None = None,
    skip_resurrections: frozenset[str] = frozenset(),
) -> list[Scorecard]:
    """Per family and citywide, for both tier sets, sorted by (family, tier set) (REQ-STAT-SF.1-.4).

    `baseline` maps an incident to its coincidence probability; without it the adjusted rate is null.
    `skip_resurrections` lists incident IDs whose zombie is not counted (REQ-STAT-CITY.1).
    """
    out: list[Scorecard] = []
    for tier_set in ("headline", "all"):
        zombies = zombie_incident_ids(result, tier_set) - skip_resurrections  # type: ignore[arg-type]
        expected: dict[str, float] = defaultdict(float)
        counts: dict[str, list[int]] = defaultdict(
            lambda: [0, 0, 0, 0]
        )  # closed, known, on time, stayed fixed
        for inc in eligible_originals(result.incidents, data_end, params, all_tiers=tier_set == "all"):
            resurrected = inc.incident_id in zombies
            p = baseline(inc) if baseline and resurrected else None
            for cid in inc.member_ids:
                c = cases[cid]
                for key in (inc.type_family, CITYWIDE):
                    row = counts[key]
                    row[0] += 1
                    if c.on_time is None:
                        continue
                    row[1] += 1
                    if c.on_time:
                        row[2] += 1
                        row[3] += 0 if resurrected else 1
                        if p is not None and resurrected:
                            expected[key] += p
        counts.setdefault(CITYWIDE, [0, 0, 0, 0])
        for family in sorted(counts):
            closed, known, on_time, stayed = counts[family]
            adj = adjusted_rate(stayed, on_time, known, expected[family]) if baseline else None
            out.append(
                Scorecard(
                    family, tier_set, closed, known, make_rate(on_time, known), make_rate(stayed, known), adj
                )  # type: ignore[arg-type]
            )
    return sorted(out, key=lambda s: (s.family, s.tier_set))


def counts_by_tier(result: DetectionResult) -> dict[str, int]:
    """Headline, `source_unknown`, `city_rereport` and `sensitivity` zombie counts, side by side (REQ-STAT-TIER.1)."""
    return {t: result.count(t) for t in ZOMBIE_TIERS}  # type: ignore[misc]


def scorecard_payload(
    cards: list[Scorecard], result: DetectionResult, data_version: str, params: Params = DEFAULT, dataset: str = "full"
) -> dict:
    """The `scorecard.json` payload (schema `scorecard`, REQ-STAT-EXP.1)."""
    return {
        "data_version": data_version,
        "dataset": dataset,  # "sample" or "full": a sample rate is not a citywide figure (ops#51)
        "params": params_json(params),
        "seed": None,  # Wilson intervals only; nothing is resampled in this file
        "scorecards": [c.to_json() for c in cards],
        "counts": counts_by_tier(result),
    }
