"""P10 part 1 (design): tour selection ignores the confidence score. REQ-STAT-TOUR.1."""

from __future__ import annotations

import random
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from undead311.detect.model import Zombie
from undead311.stats.tour import VERDICT_RANK, build_tour


def zombie(i: int, reports: int, tier: str, confidence: float, verdict: str = "not_reviewed") -> Zombie:
    return Zombie(
        incident_id=f"I{i:03d}", member_ids=(f"I{i:03d}",), resurrection_id=f"R{i:03d}", reports_after=reports,
        gap_days=1.0, match_mode="segment", distance_m=1.0, tier=tier, after_temporary_fix=False,
        source_unknown=False, chain_id=f"I{i:03d}", times_risen=1, type_family="pothole_roadway",
        coroner_label="resolved", bulk_closure=False, close_year=2024, confidence=confidence, skeptic_verdict=verdict,  # type: ignore[arg-type]
    )  # fmt: skip


zombies = st.lists(
    st.tuples(st.integers(1, 6), st.sampled_from(["headline", "headline", "source_unknown", "sensitivity"]),
              st.floats(0, 1), st.sampled_from(["not_reviewed", "survives", "weakened", "explained_away"])),
    max_size=20,
).map(lambda rows: [zombie(i, r, t, c, v) for i, (r, t, c, v) in enumerate(rows)])  # fmt: skip


@given(zombies, st.integers(0, 10_000))
def test_prop_stat_10_tour_does_not_change_when_confidence_is_permuted(zs, seed):
    """REQ-STAT-TOUR.1 (P10 part 1): same tour after shuffling confidence scores among the zombies."""
    scores = [z.confidence for z in zs]
    random.Random(seed).shuffle(scores)
    permuted = [replace(z, confidence=s) for z, s in zip(zs, scores, strict=True)]
    assert build_tour(zs) == build_tour(permuted)


@given(zombies, st.integers(0, 10_000))
def test_prop_stat_10_tour_is_headline_only_three_distinct_and_order_invariant(zs, seed):
    """REQ-STAT-TOUR.1: three distinct headline IDs, ranked by Skeptic verdict ("survives" before "weakened" before
    "not_reviewed", owner decision ops#215), then by most re-reports; input order does not matter."""
    tour = build_tour(zs)
    headline = [z for z in zs if z.tier == "headline" and z.skeptic_verdict != "explained_away"]  # ops#50
    if len(headline) < 3:
        assert tour is None
        return
    assert tour.provisional and len(set(tour.zombie_ids)) == 3
    by_id = {z.zombie_id: z for z in headline}
    assert set(tour.zombie_ids) <= set(by_id)  # never an explained_away zombie
    key = lambda z: (VERDICT_RANK[z.skeptic_verdict], -z.reports_after)
    worst_chosen = max(key(by_id[i]) for i in tour.zombie_ids)
    assert all(key(z) >= worst_chosen for z in headline if z.zombie_id not in tour.zombie_ids)
    shuffled = list(zs)
    random.Random(seed).shuffle(shuffled)
    assert build_tour(shuffled) == tour
