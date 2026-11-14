"""Credibility-layer properties: P2, P3, P4, P6, P7, P8, P9, P10 part 2 (design "Correctness properties").

REQ-STAT-KM, REQ-STAT-SHIFT, REQ-STAT-PLACEBO, REQ-STAT-BASE, REQ-STAT-EB, REQ-STAT-FUNNEL, REQ-STAT-SF.3, REQ-STAT-TIER,
REQ-STAT-VAL.2, REQ-STAT-TOUR.2; testing.md #6, #7, #8, #17.
"""

from __future__ import annotations

import random
from dataclasses import replace

from helpers import day
from hypothesis import assume, given
from hypothesis import strategies as st
from strategies import town

from undead311.detect.core import detect
from undead311.detect.model import ZOMBIE_TIERS, DetectionResult, Zombie
from undead311.stats.baseline import BaselineModel, excess_rows
from undead311.stats.groups import (
    build_groups,
    fit_kappa,
    funnel_limits,
    funnel_limits_at,
    group_counts,
    shrink,
)
from undead311.stats.rates import scorecards
from undead311.stats.shift import shift_and_placebo
from undead311.stats.survival import curves, km
from undead311.stats.temporary import temporary_rows
from undead311.stats.tour import build_tour
from undead311.stats.validation import cohen_kappa, score

END = day(400)
LABELS = ["still_broken", "fixed_since", "different_issue", "cant_tell"]


def with_on_time(cases, seed):
    rng = random.Random(seed)
    return [replace(c, on_time=rng.choice([True, False, None])) for c in cases]


@given(st.lists(st.tuples(st.integers(0, 400), st.booleans()), min_size=1, max_size=60))
def test_prop_stat_2_survival_starts_at_one_never_rises_and_bounds_stay_in_unit_interval(sample):
    """REQ-STAT-KM.1-2, testing.md #6 (P2)."""
    c = km([float(d) for d, _ in sample], [int(e) for _, e in sample])
    assert c is not None and c.survival[0] == 1.0 and c.times[0] == 0.0
    assert all(b <= a + 1e-12 for a, b in zip(c.survival, c.survival[1:], strict=False))
    assert all(0.0 <= lo <= s <= hi <= 1.0 for lo, s, hi in zip(c.lo, c.survival, c.hi, strict=True))
    for share, lo, hi in c.at.values():
        assert share is None or 0.0 <= lo <= share <= hi <= 1.0


@given(town())
def test_prop_stat_2_curves_built_from_a_detection_start_at_one(cases):
    """REQ-STAT-KM.1, .3: the headline and all-tier curves of any town."""
    for c in curves(detect(cases), END):
        assert c.survival[0] == 1.0 and 0 <= c.events <= c.n


@given(town(min_size=4), st.integers(0, 1000))
def test_prop_stat_3_excess_shift_and_placebo_are_identical_for_a_fixed_seed_and_any_input_order(cases, seed):
    """REQ-STAT-SHIFT.2, REQ-STAT-INT.1, testing.md #5 and #7 (P3)."""
    by_id = {c.id: c for c in cases}
    a = BaselineModel(by_id, detect(cases), data_end=END)
    reversed_cases = list(reversed(cases))
    b = BaselineModel({c.id: c for c in reversed_cases}, detect(reversed_cases), data_end=END)
    assert excess_rows(a, seed, 50) == excess_rows(b, seed, 50)
    assert shift_and_placebo(a, seed, 20, 3) == shift_and_placebo(b, seed, 20, 3)


@given(town(), st.integers(0, 10_000))
def test_prop_stat_6_raw_is_at_most_adjusted_is_at_most_on_time(cases, seed):
    """REQ-STAT-SF.3, testing.md #17 (P6)."""
    cases = with_on_time(cases, seed)
    result = detect(cases)
    by_id = {c.id: c for c in cases}
    model = BaselineModel(by_id, result, data_end=END)
    for c in scorecards(result, by_id, END, baseline=model.p):
        assert c.stayed_fixed_adj is not None
        if c.on_time.rate is None:
            assert c.stayed_fixed_adj.rate is None
        else:
            assert c.stayed_fixed_raw.rate <= c.stayed_fixed_adj.rate + 1e-12
            assert c.stayed_fixed_adj.rate <= c.on_time.rate + 1e-12
            assert 0 <= c.stayed_fixed_adj.lo <= c.stayed_fixed_adj.rate <= c.stayed_fixed_adj.hi <= 1


@given(town(), st.integers(0, 10_000))
def test_prop_stat_7_headline_values_ignore_other_tiers_and_all_tiers_add_up(cases, seed):
    """REQ-STAT-TIER.1-2 (P7): zombies of the other two tiers added to incidents without one leave every headline
    scorecard and excess row unchanged, and the tier counts add up to the zombie count."""
    cases = with_on_time(cases, seed)
    result = detect(cases)
    by_id = {c.id: c for c in cases}
    model = BaselineModel(by_id, result, data_end=END)
    before = [c.to_json() for c in scorecards(result, by_id, END, baseline=model.p) if c.tier_set == "headline"]
    rows_before = [r.to_json() for r in excess_rows(model, 1, 30) if r.tier_set == "headline"]
    assume(result.zombies)
    has = {z.incident_id for z in result.zombies}
    extra = [
        replace(result.zombies[0], incident_id=inc.incident_id, resurrection_id=f"X{i}",
                tier=("source_unknown", "city_rereport", "sensitivity")[(seed + i) % 3])
        for i, inc in enumerate(result.incidents) if inc.incident_id not in has
    ]  # fmt: skip
    plus = DetectionResult(**{**result.__dict__, "zombies": result.zombies + extra})
    model2 = BaselineModel(by_id, plus, data_end=END)
    after = [c.to_json() for c in scorecards(plus, by_id, END, baseline=model2.p) if c.tier_set == "headline"]
    assert before == after
    assert rows_before == [r.to_json() for r in excess_rows(model2, 1, 30) if r.tier_set == "headline"]
    assert sum(plus.count(t) for t in ZOMBIE_TIERS) == len(plus.zombies)


@given(town(), st.integers(0, 10_000))
def test_prop_stat_7_every_other_headline_statistic_ignores_added_non_headline_zombies(cases, seed):
    """REQ-STAT-TIER.1 (P7, every exported statistic): group counts and shrunk groups, funnel limits, survival curves and the
    temporary-fix `after_temporary_fix` rows keep their headline values when source_unknown or sensitivity zombies are added."""
    cases = with_on_time(cases, seed)
    result = detect(cases)
    assume(result.zombies)
    has = {z.incident_id for z in result.zombies}
    extra = [
        replace(result.zombies[0], incident_id=inc.incident_id, resurrection_id=f"X{i}",
                tier="source_unknown" if (seed + i) % 2 else "sensitivity", after_temporary_fix=False)
        for i, inc in enumerate(result.incidents) if inc.incident_id not in has
    ]  # fmt: skip
    plus = DetectionResult(**{**result.__dict__, "zombies": result.zombies + extra})
    assert group_counts(result, END, tier_set="headline") == group_counts(plus, END, tier_set="headline")
    before = build_groups(group_counts(result, END, tier_set="headline"), {})
    after = build_groups(group_counts(plus, END, tier_set="headline"), {})
    assert before[:2] == after[:2] and [g.to_json() for g in before[2]] == [g.to_json() for g in after[2]]
    assert funnel_limits(before[0], 30) == funnel_limits(after[0], 30)
    assert [c.to_json() for c in curves(result, END) if c.tier_set == "headline"] == [
        c.to_json() for c in curves(plus, END) if c.tier_set == "headline"]  # fmt: skip

    def temp(res):
        return [(r["family"], r["department"], r["n_made_safe"], r["after_temporary_fix"]) for r in temporary_rows(res, END)]

    assert temp(result) == temp(plus)


@given(
    st.lists(st.tuples(st.integers(0, 200), st.integers(1, 200)), min_size=2, max_size=25),
    st.floats(0.01, 0.99),
)
def test_prop_stat_4_each_shrunk_rate_lies_between_raw_and_citywide(groups, mu):
    """REQ-STAT-EB.1, testing.md #8 (P4)."""
    pairs = [(min(k, n), n) for k, n in groups]
    kappa, _ = fit_kappa([k for k, _ in pairs], [n for _, n in pairs], mu)
    for k, n in pairs:
        lo, hi = sorted((k / n, mu))
        assert lo <= shrink(k, n, mu, kappa) <= hi


@given(st.integers(1, 150), st.floats(0.02, 0.98))
def test_prop_stat_4_build_groups_keeps_shrunk_rates_between_raw_and_citywide(n, mu):
    counts = {("family", "a"): (int(n * mu), n), ("family", "b"): (3, 20), ("department", "d"): (1, 4)}
    city, _kappa, groups = build_groups(counts)
    assert city is not None
    for g in groups:
        lo, hi = sorted((g.raw, city))
        assert lo - 1e-12 <= g.shrunk <= hi + 1e-12 and g.lo <= g.shrunk <= g.hi


@given(st.integers(1, 400), st.floats(0.05, 0.95))
def test_prop_stat_8_funnel_limits_are_nested_and_narrow_as_n_grows(n, p0):
    """REQ-STAT-FUNNEL.1 (P8): the 99.8% limits contain the 95% ones; four times the cases never widen them."""
    lo95, hi95, lo998, hi998 = funnel_limits_at(n, p0)
    assert 0 <= lo998 <= lo95 <= hi95 <= hi998 <= 1
    assume(n >= 20)
    b = funnel_limits_at(4 * n, p0)
    assert b[1] - b[0] <= hi95 - lo95 + 1e-12 and b[3] - b[2] <= hi998 - lo998 + 1e-12


@given(st.lists(st.tuples(st.sampled_from(LABELS), st.sampled_from(LABELS)), min_size=1, max_size=40))
def test_prop_stat_9_precision_interval_contains_the_estimate_and_kappa_is_in_range(pairs):
    """REQ-STAT-VAL.2 (P9)."""
    labels = {f"z{i}": {"r1": a, "r2": b} for i, (a, b) in enumerate(pairs)}
    v = score([], labels)
    p = v.precision
    if p and p["n"]:
        assert 0 <= p["lo"] <= p["rate"] <= p["hi"] <= 1
    for k in (v.kappa, v.kappa_still_broken, cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])):
        assert k is None or -1.0 <= k <= 1.0
    assert 0.0 <= v.cant_tell_share <= 1.0


def zombie(i: int, reports: int, tier: str = "headline", verdict: str = "not_reviewed") -> Zombie:
    return Zombie(
        incident_id=f"I{i:03d}", member_ids=(f"M{i:03d}",), resurrection_id=f"R{i:03d}", reports_after=reports, gap_days=1.0,
        match_mode="segment", distance_m=1.0, tier=tier, after_temporary_fix=False, source_unknown=False, chain_id=f"C{i}",
        times_risen=1, type_family="pothole_roadway", coroner_label="resolved", bulk_closure=False, close_year=2024,
        skeptic_verdict=verdict,
    )  # fmt: skip


@given(st.lists(st.tuples(st.integers(1, 6), st.sampled_from(["headline", "headline", "source_unknown"]),
                          st.sampled_from(["not_reviewed", "survives", "explained_away"])), min_size=3, max_size=14),
       st.integers(0, 10_000))
def test_prop_stat_10_a_non_provisional_tour_contains_only_confirmed_ids(spec, seed):
    """REQ-STAT-TOUR.2 (P10 part 2)."""
    zs = [zombie(i, r, t, v) for i, (r, t, v) in enumerate(spec)]
    heads = [z.zombie_id for z in zs if z.tier == "headline" and z.skeptic_verdict != "explained_away"]
    assume(len(heads) >= 3)
    rng = random.Random(seed)
    confirmed = rng.sample(heads, rng.randint(0, len(heads))) + ["not-a-zombie"]
    tour = build_tour(zs, None, confirmed)
    assert tour is not None
    real = set(confirmed) & set(heads)
    if not tour.provisional:
        assert set(tour.zombie_ids) <= real and len(real) >= 3
    else:
        assert len(real) < 3
    named = rng.sample(heads, 3)  # an override is honored non-provisionally only when every listed ID is confirmed
    t2 = build_tour(zs, named, confirmed)
    assert t2 is not None
    if not t2.provisional:
        assert set(t2.zombie_ids) <= real
        if set(named) <= real:
            assert t2.source == "override" and set(t2.zombie_ids) == set(named)
