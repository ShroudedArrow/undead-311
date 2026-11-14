"""Results with and without city-originated re-reports (REQ-STAT-CITY.1, zombie-definition step 6).

A re-report is city-originated when it is a legacy case opened by city staff (`detect.core.is_city_originated`). The new
system records no origin, so new-system re-reports are never removed: the counts say so. A zombie is removed only when
every re-report attached to its incident is city-originated; an incident with a resident re-report keeps its zombie.
The detector is not rerun: a first re-report that is city-originated while a later one is a resident's stays a zombie
with its original tier (a small approximation, stated in METHODS.md).
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
    """Headline zombies with all re-reports, with city-originated ones removed, and what was removed (REQ-STAT-CITY.1)."""
    only = city_only_incidents(result, cases)
    headline = [z for z in result.zombies if z.tier == "headline"]
    removed = [z for z in headline if z.incident_id in only]
    unknown = [z for z in headline if cases[z.resurrection_id].system == "new"]
    return {
        "headline_all": len(headline), "headline_without_city": len(headline) - len(removed),
        "city_originated_removed": len(removed), "new_system_origin_unknown": len(unknown),
    }  # fmt: skip
