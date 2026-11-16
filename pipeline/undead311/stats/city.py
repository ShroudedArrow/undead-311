"""Results with and without city-originated re-reports (REQ-STAT-CITY.1, zombie-definition step 6).

A re-report is city-originated when it is a legacy case opened by city staff (`detect.core.is_city_originated`). The new
system records no origin, so new-system re-reports are never removed: the counts say so. A zombie is removed only when
every re-report attached to its incident is city-originated; an incident with a resident re-report keeps its zombie.
The detector is not rerun: a first re-report that is city-originated while a later one is a resident's stays a zombie
with its original tier (a small approximation, stated in METHODS.md). Since ops#29 a city-originated FIRST re-report is
its own tier (`city_rereport`, outside the headline), so `city_only_incidents` is only a safety net for the scorecards.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from undead311.detect.core import is_city_originated
from undead311.detect.model import Case, DetectionResult


def city_only_incidents(result: DetectionResult, cases: Mapping[str, Case]) -> frozenset[str]:
    """Incidents whose every attached re-report is a legacy city-originated case."""
    attached: dict[str, list[bool]] = defaultdict(list)
    for rid, iid in result.attribution.items():
        attached[iid].append(is_city_originated(cases[rid]))
    return frozenset(i for i, flags in attached.items() if flags and all(flags))


def city_counts(result: DetectionResult, cases: Mapping[str, Case]) -> dict[str, int]:
    """Headline counts with and without city-originated re-reports (REQ-STAT-CITY.1, REQ-DET-TIER.3).

    A legacy city-originated first re-report puts the zombie in the `city_rereport` tier, outside the headline (ZD step 6,
    ops#29), so `headline_without_city` is the headline itself and `city_originated_removed` is the size of that tier.
    `headline_all` is what the headline held before the tier existed. A headline zombie whose later re-report is a city
    case but whose first is a resident's keeps its place."""
    headline = [z for z in result.zombies if z.tier == "headline"]
    city_tier = result.count("city_rereport")
    unknown = [z for z in headline if cases[z.resurrection_id].system == "new"]
    return {
        "headline_all": len(headline) + city_tier, "headline_without_city": len(headline),
        "city_originated_removed": city_tier, "new_system_origin_unknown": len(unknown),
    }  # fmt: skip
