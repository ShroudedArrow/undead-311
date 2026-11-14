"""Credibility-layer unit tests, by hand: REQ-STAT-KM, -EB, -FUNNEL, -REP, -SHIFT, -PLACEBO, -TEMP, -CITY, -GRID, -VAL, -TOUR.2,
-EXP.1-2, -TIER, -SF.3."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import date

import duckdb
import numpy as np
import pytest
from helpers import day, mk
from test_pipeline import raw_folder

from undead311.detect.core import detect
from undead311.detect.grid import run_grid, store_grid
from undead311.detect.params import DEFAULT
from undead311.export.writers import validate
from undead311.ingest.geometry import store_neighborhood_geometry
from undead311.pipeline import run_pipeline
from undead311.stats.baseline import BaselineModel, excess_rows
from undead311.stats.city import city_counts, city_only_incidents
from undead311.stats.cohort import eligible_originals, spot_key
from undead311.stats.gridstats import GridMetrics, grid_payload, store_grid_metrics
from undead311.stats.groups import (
    build_groups,
    fit_kappa,
    funnel_limits,
    funnel_limits_at,
    funnel_ns,
    intensity_by_family,
    intensity_by_neighborhood,
    shrink,
)
from undead311.stats.rates import adjusted_rate, scorecards
from undead311.stats.shift import shift_and_placebo
from undead311.stats.survival import SURVIVAL_HORIZON_DAYS, curves, horizon_params, km, survival_payload
from undead311.stats.temporary import separate_death_counts, temporary_payload, temporary_rows
from undead311.stats.tour import build_tour
from undead311.stats.validation import (
    cohen_kappa,
    draw_sample,
    norm_label,
    read_config,
    read_labels,
    render_section,
    run_validate,
    run_validation_sample,
    score,
)

END = day(300)


# --- survival ---------------------------------------------------------------------------------------------------------
def test_req_stat_km_2_kaplan_meier_on_a_five_case_toy_by_hand():
    """Times 2, 3, 3, 5, 7 with events 1, 1, 0, 1, 0: S(2) = 4/5, S(3) = 4/5 * 3/4, S(5) = 0.6 * 1/2 = 0.3."""
    c = km([2, 3, 3, 5, 7], [1, 1, 0, 1, 0])
    assert c.times == (0.0, 2.0, 3.0, 5.0, 7.0)
    assert c.survival == pytest.approx((1.0, 0.8, 0.6, 0.3, 0.3))
    assert c.half_life == 5.0 and c.at[7][0] == pytest.approx(0.3) and c.at[30] == (None, None, None)
    assert all(lo <= s <= hi for lo, s, hi in zip(c.lo, c.survival, c.hi, strict=True))


def test_req_stat_km_2_no_crossing_means_no_half_life():
    c = km([10, 20, 30, 40, 50, 60], [0, 0, 0, 1, 0, 0])  # at 40, 3 at risk: S = 2/3 and never reaches 0.5
    assert c.half_life is None and c.survival[-1] == pytest.approx(2 / 3)


def test_req_stat_km_1_the_survival_run_changes_only_the_window():
    p = horizon_params(replace(DEFAULT, RADIUS_M=50))
    assert p.WINDOW_DAYS == SURVIVAL_HORIZON_DAYS == 365 and p.RADIUS_M == 50


def test_req_stat_km_1_a_resurrection_after_the_window_still_counts_at_the_horizon():
    cs = [mk("A", 0, 1), mk("RA", 100)] + [mk(f"B{i}", 0, 1, x=500.0 * (i + 1)) for i in range(11)]
    p = horizon_params()
    res = detect(cs, p)
    assert any(z.incident_id == "A" for z in res.zombies)  # 99 days after the closure: outside 60 days, inside 365
    assert not any(z.incident_id == "A" for z in detect(cs).zombies)
    all_curve = next(c for c in curves(res, day(500)) if c.name == "all" and c.tier_set == "headline")
    assert all_curve.n == 12 and all_curve.events == 1
    assert all_curve.at[90][0] == pytest.approx(1.0) and all_curve.at[30][0] == 1.0  # the event is at day 99, after day 90


def test_req_stat_km_3_headline_and_all_tier_curves_differ_by_tier():
    cs = [mk("M", 0, 1, label="made_safe_temporary"), mk("RM", 10, system="new")] + [
        mk(f"B{i}", 0, 1, x=500.0 * (i + 1)) for i in range(11)
    ]
    res = detect(cs, horizon_params())
    by = {(c.name, c.tier_set): c for c in curves(res, day(500))}
    assert by[("all", "headline")].events == 0 and by[("all", "all")].events == 1


def test_req_stat_exp_1_survival_payload_validates():
    cs = [mk("A", 0, 1), mk("RA", 10)]
    res = detect(cs, horizon_params())
    validate("survival", survival_payload(res, {c.id: c for c in cs}, day(500), "v", horizon_params(), "sample"))


# --- shrinkage and funnel ------------------------------------------------------------------------------------------------
def test_req_stat_eb_1_shrunk_rate_by_hand():
    assert shrink(0, 10, 0.2, 10.0) == pytest.approx(0.1)  # (0 + 0.2 * 10) / (10 + 10)
    assert shrink(5, 10, 0.2, 10.0) == pytest.approx(0.35)  # (5 + 2) / 20, between 0.5 and 0.2
    assert shrink(3, 0, 0.2, 10.0) == 0.2


def test_req_stat_eb_1_a_homogeneous_set_of_groups_is_shrunk_hard_and_an_overdispersed_one_is_not():
    same, _ = fit_kappa([2, 2, 2, 2], [10, 10, 10, 10], 0.2)
    spread, _ = fit_kappa([0, 10, 1, 9], [10, 10, 10, 10], 0.5)
    assert same > spread and spread < 5


def test_req_stat_funnel_1_exact_binomial_limits_by_hand():
    """Bin(10, 0.5): the 2.5% and 97.5% quantiles are 2 and 8, the 0.1% and 99.9% ones 1 and 9."""
    assert funnel_limits_at(10, 0.5) == (0.2, 0.8, 0.1, 0.9)


def test_req_stat_funnel_1_limits_cover_every_n_up_to_the_largest_and_keep_the_file_small():
    ns = funnel_ns(100_000)
    assert ns[0] == 1 and ns[-1] == 100_000 and ns[:500] == list(range(1, 501)) and len(ns) < 800
    assert [r["n"] for r in funnel_limits(0.1, 30)] == list(range(1, 31)) and funnel_limits(None, 30) == []


def test_req_stat_funnel_2_unusual_only_outside_the_998_limits_and_neighborhoods_need_intensity():
    counts = {("family", "a"): (50, 1000), ("family", "b"): (50, 1000), ("department", "tiny"): (1, 2),
              ("department", "odd"): (150, 1000), ("neighborhood", "N"): (50, 1000)}  # fmt: skip
    city, _kappa, groups = build_groups(counts, {})
    by = {(g.kind, g.name): g for g in groups}
    assert city == pytest.approx(0.05) and ("neighborhood", "N") not in by  # REQ-STAT-REP.2: no intensity, no neighborhood
    assert by[("department", "odd")].unusual is True and by[("department", "tiny")].unusual is False
    _c, _k, with_km = build_groups(counts, {"N": 12.5})
    assert next(g for g in with_km if g.kind == "neighborhood").reports_per_km == 12.5


def test_req_stat_rep_1_reports_per_km_by_neighborhood():
    cs = {c.id: replace(c, neighborhood="Roxbury") for c in [mk("A", 0, 1), mk("B", 1), mk("C", 2)]}
    assert intensity_by_neighborhood(cs, {"Roxbury": 1.5, "Nowhere": 2.0, "Empty": 0.0}) == {"Roxbury": 2.0}


def test_req_stat_rep_1_a_mirror_copy_is_counted_once_in_reports_per_km():
    """ZD step 9, REQ-STAT-REP.1 (ops#127): the later copy of a cross-system mirror pair is one report, so it adds nothing."""
    cs = {c.id: replace(c, neighborhood="Roxbury") for c in [mk("A", 0, 1), mk("B", 1), mk("C", 2)]}
    km = {"Roxbury": 1.5}
    assert intensity_by_neighborhood(cs, km, frozenset({"C"})) == {"Roxbury": pytest.approx(2 / 1.5)}
    rows = intensity_by_family(cs, km, frozenset({"B", "C"}))
    assert [r["reports"] for r in rows] == [1]
    assert intensity_by_family(cs, km) != rows  # without the skip every case counts


# --- adjusted rate, tiers ---------------------------------------------------------------------------------------------------
def test_req_stat_sf_3_adjusted_rate_by_hand_and_the_clamp():
    """10 on-time cases, 6 stayed fixed, 4 resurrected; 1.5 coincidences expected: (6 + 1.5) / 12 known."""
    r = adjusted_rate(6, 10, 12, 1.5)
    assert r.rate == pytest.approx(7.5 / 12) and r.k == 8 and r.lo <= r.rate <= r.hi
    assert adjusted_rate(6, 10, 12, 99.0).rate == pytest.approx(10 / 12)  # capped: never above the on-time rate
    assert adjusted_rate(6, 10, 12, -3.0).rate == pytest.approx(6 / 12)
    assert adjusted_rate(0, 0, 0, 1.0).reason == "no_cases"


def test_req_stat_sf_3_without_a_baseline_the_adjusted_rate_is_null():
    cs = [replace(mk("A", 0, 1), on_time=True)]
    c = scorecards(detect(cs), {x.id: x for x in cs}, END)[0]
    assert c.stayed_fixed_adj is None


# --- baseline hook and shift ----------------------------------------------------------------------------------------------
def spot_town():
    cs = []
    for s in range(30):
        t = 0.0
        while t < 400:
            cs.append(mk(f"S{s:02d}-{int(t):03d}", t, t + 2, x=s * 400.0))
            t += 37.0 + s % 5
    return cs


def test_req_stat_shift_1_the_distribution_is_reported_beside_the_observed_count_and_is_seeded():
    cs = spot_town()
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(420))
    a, pa = shift_and_placebo(m, 311, 100, 5)
    b, pb = shift_and_placebo(m, 311, 100, 5)
    c, _ = shift_and_placebo(m, 7, 100, 5)
    assert a == b and pa == pb and a != c
    assert a.runs == 100 and a.q025 <= a.mean <= a.q975 and a.observed > 0
    assert len(a.counts) == 100 and a.headline_zombies == sum(z.tier == "headline" for z in res.zombies)
    j = a.to_json()
    assert set(j) == {"runs", "seed", "observed", "mean", "q025", "q975", "headline_zombies"}


def test_req_stat_placebo_2_the_warning_is_set_exactly_when_the_interval_excludes_zero():
    cs = spot_town()
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(420))
    _s, p = shift_and_placebo(m, 311, 50, 5)
    assert p.calibration_warning == (p.lo > 0 or p.hi < 0) and p.lo <= p.excess <= p.hi
    assert shift_and_placebo(BaselineModel({}, detect([]), data_end=day(10)), 1, 10, 2) == (None, None)


def null_town(gap, spots=120, span=1000, seed=5, close_after=2.0):
    """Reports at Poisson times at every spot, each closed `close_after` days after it opens: nothing is a resurrection by cause,
    so every statistic that compares with chance should find none."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(spots):
        t, n = 0.0, 0
        while True:
            t += rng.exponential(gap)
            if t > span:
                break
            out.append(mk(f"S{s:03d}-{n:03d}", t, t + close_after, x=s * 1000.0, segment=f"seg{s}"))
            n += 1
    return out


def test_req_stat_shift_1_and_placebo_1_on_a_town_with_no_resurrections_the_observed_count_is_inside_the_shift_interval():
    """REQ-STAT-SHIFT.1, REQ-STAT-PLACEBO.1-2 (ops#102, S29): the incident's own members are not chance hits, so a town whose
    reports are independent of closures lands inside its shift distribution and the placebo does not warn."""
    cs = null_town(200.0)
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1000))
    shift, placebo = shift_and_placebo(m, 311, 200, 10)
    assert shift.q025 <= shift.observed <= shift.q975
    assert placebo.calibration_warning is False and placebo.lo <= 0 <= placebo.hi


def test_req_stat_base_1_a_dense_null_town_never_manufactures_an_excess_and_the_shift_test_still_holds():
    """REQ-STAT-BASE.1-2, REQ-STAT-SHIFT.1 (ops#114): a report every 60 days at 120 spots, nothing resurrecting by cause. Every
    closure leaves out the 60 days after it, so about two thirds of the time is out and each spot's live time is a few windows.
    The estimate then runs 3-7 points high (p 0.67-0.70 against 0.63-0.66 observed), so the excess is zero or below and
    never positive: the direction that understates resurrections. The placebo does warn here, because it shifts closures
    independently of the reports and so cannot reproduce that dependence. Both facts are in docs/METHODS.md (Limits)."""
    cs = null_town(60.0)
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1000))
    shift, _placebo = shift_and_placebo(m, 311, 200, 10)
    assert shift.q025 <= shift.observed <= shift.q975
    row = next(r for r in excess_rows(m, 311, 200) if r.kind == "family" and r.tier_set == "headline")
    assert row.lo <= 0.0 and row.excess <= row.hi  # the interval does not sit above 0: no excess is manufactured


def test_req_stat_shift_1_own_member_reports_are_never_counted_when_a_closure_is_moved():
    """REQ-STAT-SHIFT.1 (ops#102): the closure of an incident moved to before its own members must not count them, while a
    neighbouring incident's reports still count."""
    from undead311.stats.shift import _build, _hits

    cs = [mk("Z", 5, 6), mk("A", 100, 101), mk("B", 100.5, 102)]  # A and B are one incident; Z is another at the same spot
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(400))
    sp = _build(m)
    assert sp is not None and sp.own_inc.size == 3  # every member is in the spot's group
    ids = sorted(i.incident_id for i in res.incidents)
    ab = ids.index(next(i.incident_id for i in res.incidents if set(i.member_ids) == {"A", "B"}))
    t_min = min(float(m.groups[k][0][0]) for k in sp.keys)
    early = np.full((len(ids), 1), day(90).timestamp())  # (90, 150] holds A and B (and not Z)
    hits = _hits(sp, t_min, m.window_s, early)[:, 0]
    assert hits[ab] == 0 and hits.sum() == 1  # the A+B incident does not count its own members; Z counts them


def test_req_stat_base_2_the_excess_interval_carries_the_error_of_the_pooled_baseline_and_covers_zero_on_a_null_town():
    """REQ-STAT-BASE.2-3, REQ-STAT-INT.1 (ops#103, S30): with a pooled fallback p estimated from few windows, resampling originals
    alone would give a narrow interval that excludes 0 on a town where nothing resurrects by cause."""
    cs = null_town(20.0, spots=60, span=700)
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(700))
    rows = [r for r in excess_rows(m, 311, 300) if r.kind == "family" and r.tier_set == "headline"]
    assert rows and m.fallback_counts(res.incidents)["citywide"] > len(res.incidents) // 2
    assert all(r.lo <= 0 <= r.hi for r in rows)


@pytest.mark.parametrize("gap", [400.0, 300.0])
def test_req_stat_base_1_and_placebo_1_sparse_null_towns_get_an_unbiased_baseline_a_covering_interval_and_no_warning(gap):
    """REQ-STAT-BASE.1-2, REQ-STAT-PLACEBO.1-2 (ops#107, S34): 300 spots with a report every 300-400 days on average and no
    resurrections by cause. The share-of-windows p_spot came out 0.21 against an observed 0.14 here, so the excess interval
    excluded 0 in 5 of 8 towns and the placebo warned in 8 of 8. Seeds 5-12 are the ones the review used."""
    p_mean, observed, covered, warned = [], [], 0, 0
    for seed in range(5, 13):
        cs = null_town(gap, spots=300, span=1400, seed=seed)
        res = detect(cs)
        m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1400))
        zs = {z.incident_id for z in res.zombies if z.tier == "headline"}
        spot = [i for i in eligible_originals(res.incidents, m.data_end) if m.estimate(i).source == "spot"]
        p_mean.append(np.mean([m.estimate(i).p for i in spot]))
        observed.append(np.mean([i.incident_id in zs for i in spot]))
        row = next(r for r in excess_rows(m, 311, 200) if r.kind == "family" and r.tier_set == "headline")
        covered += row.lo <= 0 <= row.hi
        warned += shift_and_placebo(m, 311, 100, 10)[1].calibration_warning
    assert abs(np.mean(p_mean) - np.mean(observed)) < 0.02  # was 0.07 and more
    assert covered >= 7 and warned <= 2  # nominal level 95% and 5%


def test_req_stat_base_1_a_busy_spot_does_not_raise_its_own_baseline():
    """REQ-STAT-BASE.1 (ops#107): leaving the incident's own reports out means five duplicate reports at one spot, all in one
    incident, give that incident p_spot 0 (the spot's first report is never a chance report either)."""
    own = [mk(f"O{i}", 100 + 0.1 * i, 101 + 0.1 * i) for i in range(5)]  # one incident of five duplicates
    cs = [mk("F", 0, 1)] + own  # F is the spot's first report
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1500))
    inc = next(i for i in res.incidents if "O0" in i.member_ids)
    assert set(inc.member_ids) == {f"O{i}" for i in range(5)}
    assert m.own_after(inc).sum() == 5
    summer = m.spot_p(inc, 2)  # days 100-101 are in June
    assert summer is not None and summer[0] == 0.0  # F is the first report and the five duplicates are the incident's own
    extra = [*cs, mk("X", 90)]  # one other live report in the same season changes it
    res2 = detect(extra)
    m2 = BaselineModel({c.id: c for c in extra}, res2, data_end=day(1500))
    assert m2.spot_p(next(i for i in res2.incidents if "O0" in i.member_ids), 2)[0] > 0.0


def test_req_stat_int_1_the_bootstrap_interval_holds_its_point_estimate_when_every_cell_is_0_or_1():
    """REQ-STAT-INT.1, REQ-STAT-BASE.2 (ops#108, S35): a draw clipped to [0, 1] and re-centred left the mean draw above 0, so
    with 2,000 non-zombie originals at zero-hit cells the interval was [-122.9, -99.8] around a point estimate of 0."""
    from undead311.stats.intervals import bootstrap_sum_cells

    n = 2000
    for p_hat, hit in ((0.0, 0.0), (1.0, 1.0)):
        cells = [i % 3 for i in range(n)]
        values = [hit - p_hat] * n  # observed minus expected = 0 for every original
        for n_eff in (4.0, 15.0, 40.0):
            lo, hi = bootstrap_sum_cells(values, cells, [p_hat] * 3, [n_eff] * 3, np.random.default_rng(1), 200)
            assert lo <= 0.0 <= hi
    # a cell at 0.5 does move the interval, and it is centred on the point estimate
    lo, hi = bootstrap_sum_cells([-0.5] * 1000, [0] * 1000, [0.5], [20.0], np.random.default_rng(1), 400)
    assert lo < -500 < hi and hi - lo > 50


def test_req_stat_int_1_clusters_are_resampled_whole():
    """REQ-STAT-INT.1, REQ-STAT-BASE.2: two clusters of 10 with opposite signs. Resampling originals one by one would give a
    narrow interval around 0; resampling the two clusters gives sums of -10 / 0 / 10."""
    from undead311.stats.intervals import bootstrap_sum_cells

    values = [1.0] * 10 + [-1.0] * 10
    clusters = [0] * 10 + [1] * 10
    lo, hi = bootstrap_sum_cells(values, [-1] * 20, [], [], np.random.default_rng(3), 400, clusters=clusters)
    assert (lo, hi) == (-20.0, 20.0)
    single = bootstrap_sum_cells(values, [-1] * 20, [], [], np.random.default_rng(3), 400)
    assert single[1] - single[0] < hi - lo


def test_req_stat_eb_2_every_exported_group_carries_raw_shrunk_interval_and_n():
    """REQ-STAT-EB.2 (ops#109, S36): raw rate, shrunk rate, interval and n for every group of every kind."""
    counts = {}
    for name, k in (("D1", 2), ("D2", 38), ("D3", 20)):
        counts[("department", name)] = (k, 40)
    for name, k in (("N1", 20), ("N2", 21)):
        counts[("neighborhood", name)] = (k, 40)
    for name, k in (("f1", 50), ("f2", 50)):
        counts[("family", name)] = (k, 100)
    _mu, _kappas, groups = build_groups(counts, {"N1": 1.0, "N2": 1.0})
    assert {g.kind for g in groups} == {"department", "family", "neighborhood"}
    for g in groups:
        j = g.to_json()
        assert {"raw", "shrunk", "lo", "hi", "n"} <= set(j)
        assert j["n"] > 0 and None not in (j["raw"], j["shrunk"], j["lo"], j["hi"])
        assert j["lo"] <= j["shrunk"] <= j["hi"]


def test_req_stat_grid_1_a_radius_mode_run_keys_snapped_cases_by_cell_not_by_segment():
    """REQ-STAT-GRID.1 (ops#104, S31): in radius matching segments are ignored, so a snapped case's spot is its 2 x RADIUS_M cell."""
    radius = replace(DEFAULT, matching="radius")
    assert spot_key("SEG-1", 42.3, -71.1, DEFAULT) == "seg:SEG-1"
    assert spot_key("SEG-1", 42.3, -71.1, radius).startswith("cell:")
    assert spot_key("SEG-1", 42.3, -71.1, radius) == spot_key(None, 42.3, -71.1, radius)
    assert spot_key("SEG-1", 42.3, -71.1, replace(radius, RADIUS_M=15)) != spot_key("SEG-1", 42.3, -71.1015, radius)
    cs = [mk("A", 0, 1, segment="SEG-1"), mk("R", 10, segment="SEG-1", x=300.0)]  # 300 m apart on one long segment
    m = BaselineModel({c.id: c for c in cs}, detect(cs, radius), radius, day(300))
    assert all(key[1].startswith("cell:") for key in m.groups)


def test_req_stat_eb_1_kappa_is_fitted_per_kind_over_groups_that_partition_the_originals():
    """REQ-STAT-EB.1 (ops#105, S32): departments vary a lot and neighborhoods hardly at all, so one kappa for both is wrong for each."""
    counts = {}
    for name, k in (("D1", 2), ("D2", 38), ("D3", 20), ("D4", 5), ("D5", 33)):
        counts[("department", name)] = (k, 40)
    for name, k in (("N1", 20), ("N2", 21), ("N3", 19), ("N4", 20), ("N5", 20)):
        counts[("neighborhood", name)] = (k, 40)
    for name, k in (("f1", 50), ("f2", 50)):
        counts[("family", name)] = (k, 100)
    mu, kappas, groups = build_groups(counts, {n: 1.0 for n in ("N1", "N2", "N3", "N4", "N5")})
    assert mu == 0.5 and set(kappas) == {"department", "family", "neighborhood"}
    assert kappas["neighborhood"] > 20 * kappas["department"]
    assert {g.kind for g in groups} == {"department", "family", "neighborhood"}


# --- temporary fixes, city, exclusions --------------------------------------------------------------------------------------------
def test_req_stat_temp_1_share_of_made_safe_originals_that_came_back_by_hand():
    cs = [
        mk("M1", 0, 1, x=0, label="made_safe_temporary"), mk("R1", 10, x=0),  # resident, legacy: after_temporary_fix
        mk("M2", 0, 1, x=500, label="made_safe_temporary"), mk("R2", 10, x=500, system="new"),  # source_unknown
        mk("M3", 0, 1, x=1000, label="made_safe_temporary"),  # never came back
        mk("X", 0, 1, x=1500), mk("RX", 10, x=1500),  # resolved, not made safe: left out
    ]  # fmt: skip
    rows = {(r["family"], r["department"]): r for r in temporary_rows(detect(cs), END)}
    row = rows[("all", None)]
    assert row["n_made_safe"] == 3
    assert (row["after_temporary_fix"]["k"], row["source_unknown"]["k"]) == (1, 1)
    assert row["after_temporary_fix"]["rate"] == pytest.approx(1 / 3) and row["source_unknown"]["lo"] is not None


def test_req_stat_temp_2_separate_deaths_are_counted_and_exclusions_ride_along():
    cs = [mk("D", 0, 1, label="duplicate"), mk("RD", 10), mk("I", 0, 1, x=500, label="invalid"), mk("RI", 10, x=500)]
    assert separate_death_counts(detect(cs)) == {"duplicate": 1, "invalid": 1}
    payload = temporary_payload(detect(cs), END, "v", DEFAULT, "full", {"placeholder": 4})
    validate("temporary_fixes", payload)
    assert payload["exclusions"]["placeholder"] == 4 and payload["separate_deaths"]["duplicate"] == 1


def test_req_stat_city_1_a_city_first_re_report_is_its_own_tier_and_a_later_one_changes_nothing():
    """REQ-STAT-CITY.1, REQ-DET-TIER.3 (ops#29): a city-originated first re-report puts the zombie in the city tier, outside
    the headline; a resident's first re-report keeps it in the headline even when a city case follows."""
    cs = [
        mk("A", 0, 1, x=0), mk("RA", 10, x=0, source="Employee Generated"),  # only city: its own tier
        mk("B", 0, 1, x=500), mk("RB1", 10, x=500), mk("RB2", 12, x=500, source="Employee Generated"),  # resident first
        mk("C", 0, 1, x=1000), mk("RC", 10, x=1000, system="new", source=None),  # origin unknown: headline
    ]  # fmt: skip
    res = detect(cs)
    by = {c.id: c for c in cs}
    assert city_only_incidents(res, by) == {"A"}
    assert {z.incident_id: z.tier for z in res.zombies} == {"A": "city_rereport", "B": "headline", "C": "headline"}
    assert city_counts(res, by) == {
        "headline_all": 3, "headline_without_city": 2, "city_originated_removed": 1, "new_system_origin_unknown": 1,
    }  # fmt: skip
    cards = {(c.family, c.tier_set): c for c in scorecards(res, {c.id: replace(c, on_time=True) for c in cs}, END,
                                                           skip_resurrections=city_only_incidents(res, by))}  # fmt: skip
    assert cards[("citywide", "headline")].stayed_fixed_raw.k == cards[("citywide", "headline")].on_time.k - 2


# --- sensitivity grid ----------------------------------------------------------------------------------------------------------
def test_req_stat_grid_1_every_point_has_counts_excess_and_stayed_fixed_and_the_run_without_street_light_other():
    cs = [replace(c, on_time=True) for c in [mk("A1", 0, 2), mk("A2", 5), mk("B1", 0, 2, x=200), mk("B2", 40, x=225), mk("LATE", 400, x=9000)]]
    slo = [replace(mk("E1", 0, 2, x=800, family="streetlight", system="new"), type_raw="Street Light Other"),
           replace(mk("E2", 8, x=804, family="streetlight", system="new"), type_raw="Street Light Other")]  # fmt: skip
    con = duckdb.connect()
    metrics = GridMetrics()
    runs = run_grid(con, cs + slo, observer=metrics)
    store_grid(con, runs)
    store_grid_metrics(con, metrics)
    payload = grid_payload(con, "v", DEFAULT, "sample")
    validate("sensitivity_grid", payload)
    assert len(payload["points"]) == 18 and set(metrics.rows) == {r.run_id for r in runs}
    assert all(p["excess"] is not None and 0 <= p["stayed_fixed_rate"] <= 1 for p in payload["points"])
    wo = payload["without_street_light_other"]
    assert wo["all_tiers"] >= wo["headline"] >= 0
    assert grid_payload(duckdb.connect(), "v", DEFAULT, "sample") is None  # no grid tables, no file


# --- validation ----------------------------------------------------------------------------------------------------------------
def test_req_stat_val_labels_read_in_any_spelling():
    assert [norm_label(x) for x in ("still broken", "Still_Broken", "fixed since", "different issue", "can't tell", "can’t tell", "Cannot tell", "?")] == [
        "still_broken", "still_broken", "fixed_since", "different_issue", "cant_tell", "cant_tell", "cant_tell", None]  # fmt: skip


def test_req_stat_val_2_precision_cant_tell_share_and_kappa_by_hand():
    """REQ-STAT-VAL.2, REQ-STAT-VAL.3 (the confirmed set is the zombies both raters call still broken).

    z1 both still broken; z2 still broken / fixed since; z3 can't tell / still broken; z4 both fixed since."""
    labels = {"z1": {"a": "still_broken", "b": "still_broken"}, "z2": {"a": "still_broken", "b": "fixed_since"},
              "z3": {"a": "cant_tell", "b": "still_broken"}, "z4": {"a": "fixed_since", "b": "fixed_since"},
              "z5": {"a": "still_broken"}}  # fmt: skip
    v = score([], labels)
    assert v.status == "scored" and v.n_paired == 4 and v.confirmed == ("z1",)
    assert (v.precision["k"], v.precision["n"]) == (1, 3) and v.cant_tell_share == 0.25
    # four labels: po = 2/4; pe = (2*2 + 1*2 + 0) / 16 = 0.375; kappa = 0.125 / 0.625
    assert v.kappa == pytest.approx(0.2)
    assert cohen_kappa(["x", "x"], ["x", "x"]) is None  # chance agreement is 1: undefined
    assert score([], {}).status == "awaiting_field_labels" and score([], {"z": {"a": "still_broken"}}).precision is None


def test_req_stat_val_1_the_sample_is_seeded_recent_headline_in_the_configured_neighborhoods_and_blind(tmp_path):
    zs = [{"zombie_id": f"Z{i:03d}", "incident_id": "I", "resurrection_id": "R", "type_family": "sign", "tier": "headline",
           "neighborhood": "Roxbury" if i % 2 else "Dorchester", "resurrection_date": f"2026-11-{1 + i % 12:02d}",
           "confidence": 0.9} for i in range(60)]  # fmt: skip
    zs += [{"zombie_id": "OLD", "tier": "headline", "neighborhood": "Roxbury", "resurrection_date": "2026-01-01"},
           {"zombie_id": "SU", "tier": "source_unknown", "neighborhood": "Roxbury", "resurrection_date": "2026-11-10"}]  # fmt: skip
    cfg = {"neighborhoods": ["Roxbury"], "seed": 5, "n": 10}
    a = draw_sample(zs, cfg, date(2026, 11, 13))
    assert a == draw_sample(list(reversed(zs)), cfg, date(2026, 11, 13)) and len(a) == 10
    assert all(r["neighborhood"] == "Roxbury" and r["zombie_id"] not in ("OLD", "SU") for r in a)
    assert all("confidence" not in r for r in a) and a != draw_sample(zs, {**cfg, "seed": 6}, date(2026, 11, 13))
    labels = tmp_path / "labels"
    labels.mkdir()
    zj = tmp_path / "zombies.json"
    zj.write_text(json.dumps({"zombies": zs}))
    code, msg = run_validation_sample(labels, zj, date(2026, 11, 13))
    assert code == 0 and "owner chooses" in msg and not (labels / "validation_sample.csv").exists()  # no config yet
    (labels / "validation_config.json").write_text(json.dumps(cfg))
    code, msg = run_validation_sample(labels, zj, date(2026, 11, 13))
    rows = list(csv.DictReader((labels / "validation_sample.csv").open()))
    assert code == 0 and len(rows) == 10 and "confidence" not in rows[0]
    first = (labels / "validation_sample.csv").read_text()
    assert "stays as committed" in run_validation_sample(labels, zj, date(2026, 11, 20))[1]
    assert (labels / "validation_sample.csv").read_text() == first
    assert read_config(labels / "nope.json") is None


def test_req_stat_val_4_missing_labels_say_awaiting_and_exit_zero_then_scored_labels_fill_both_outputs(tmp_path):
    labels, md, out = tmp_path / "l", tmp_path / "VALIDATION.md", tmp_path / "validation.json"
    labels.mkdir()
    md.write_text("# Validation\n\nCoroner text.\n")
    code, msg = run_validate(labels, md, out, "v")
    assert code == 0 and "awaiting" in msg and json.loads(out.read_text())["status"] == "awaiting_field_labels"
    validate("validation", json.loads(out.read_text()))
    (labels / "validation_labels.csv").write_text(
        "zombie_id,rater,label,visited_on\nz1,a,still broken,2026-11-20\nz1,b,still broken,2026-11-20\n"
        "z2,a,fixed since,2026-11-20\nz2,b,can't tell,2026-11-20\n"
    )
    code, msg = run_validate(labels, md, out, "v")
    text = md.read_text()
    assert code == 0 and "Coroner text." in text and "Precision" in text and text.count("field-validation:start") == 1
    run_validate(labels, md, out, "v")
    assert md.read_text() == text  # a rerun gives the same bytes
    validate("validation", json.loads(out.read_text()))
    assert json.loads(out.read_text())["confirmed"] == ["z1"] and read_labels(labels / "validation_labels.csv")["z2"]["b"] == "cant_tell"
    assert "Awaiting" in render_section(score([], {}))


def test_req_stat_tour_2_a_confirmed_set_of_three_makes_the_tour_final_and_confirmed_only():
    cs = []
    for n, (name, reports) in enumerate([("Z1", 3), ("Z2", 2), ("Z3", 2), ("Z4", 1)]):
        cs.append(mk(f"{name}-O", 0, 1, x=500.0 * n))
        cs += [mk(f"{name}-R{k}", 5 + k, x=500.0 * n) for k in range(reports)]
    res = detect(cs)
    ids = {n: f"{n}-O:{n}-R0" for n in ("Z1", "Z2", "Z3", "Z4")}
    two = build_tour(res.zombies, None, [ids["Z4"], ids["Z3"]])
    assert two.provisional is True and ids["Z4"] not in two.zombie_ids or two.provisional
    three = build_tour(res.zombies, None, [ids["Z4"], ids["Z3"], ids["Z2"]])
    assert three.provisional is False and set(three.zombie_ids) == {ids["Z4"], ids["Z3"], ids["Z2"]}
    assert three.zombie_ids == (ids["Z2"], ids["Z3"], ids["Z4"])  # most re-reports first, ties by ID
    named = [ids["Z4"], ids["Z3"], ids["Z2"]][::-1]
    assert build_tour(res.zombies, named, list(ids.values())).source == "override"
    assert build_tour(res.zombies, [ids["Z1"], ids["Z2"], ids["Z3"]], [ids["Z4"], ids["Z3"], ids["Z2"]]).source == "most_reports"
    validate("judge_tour", three.to_json("v"))


# --- geometry -----------------------------------------------------------------------------------------------------------------------
def test_req_stat_nbr_2_areas_in_m2_and_street_km_per_neighborhood_name(tmp_path):
    def ring(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]

    def poly(name, *r):
        return {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [ring(*r)]}}

    geo = tmp_path / "b.geojson"
    geo.write_text(json.dumps({"type": "FeatureCollection", "features": [
        poly("Allston", -71.10, 42.30, -71.09, 42.31), poly("Brighton", -71.09, 42.30, -71.08, 42.31),
        poly("Roxbury", -71.20, 42.30, -71.19, 42.31)]}))  # fmt: skip
    seg = tmp_path / "s.geojson"
    line = lambda sid, a, b: {"type": "Feature", "properties": {"SEGMENT_ID": sid}, "geometry": {"type": "LineString", "coordinates": [a, b]}}
    seg.write_text(json.dumps({"type": "FeatureCollection", "features": [
        line(1, [-71.10, 42.305], [-71.09, 42.305]), line(2, [-71.19, 42.305], [-71.20, 42.305])]}))  # fmt: skip
    con = duckdb.connect()
    assert store_neighborhood_geometry(con, None) == 0 and con.execute("select count(*) from neighborhood_areas").fetchone()[0] == 0
    assert store_neighborhood_geometry(con, geo, seg) == 2
    rows = {n: (a, k) for n, a, k in con.execute("select * from neighborhood_areas").fetchall()}
    side = 0.01 * 111_320.0
    assert rows["Allston / Brighton"][0] == pytest.approx(2 * side * side * 0.7405, rel=0.01)  # two 0.01 deg squares at 42.3 N
    assert rows["Allston / Brighton"][1] == pytest.approx(0.01 * 111_320.0 * 0.7405 / 1000.0, rel=0.01)
    assert rows["Roxbury"][1] == pytest.approx(rows["Allston / Brighton"][1], rel=0.01)


# --- the whole stage -----------------------------------------------------------------------------------------------------------------
def test_req_stat_exp_1_a_pipeline_run_writes_and_validates_every_stats_file(tmp_path):
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "d", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    stats = out / "stats"
    names = {p.name for p in stats.glob("*.json")}
    assert {"scorecard.json", "judge_tour.json", "excess.json", "survival.json", "funnel.json", "groups.json",
            "sensitivity_grid.json", "temporary_fixes.json", "validation.json", "stats_status.json"} == names | {"judge_tour.json"}  # fmt: skip
    for p in sorted(stats.glob("*.json")):
        payload = json.loads(p.read_text())
        if p.name != "stats_status.json":
            validate(p.stem, payload)
            assert payload["data_version"] == rep.data_version and "params" in payload and "seed" in payload
    z = json.loads((out / "zombies.json").read_text())["zombies"][0]
    assert z["baseline_p"] is not None and rep.baseline_zombies == 1  # REQ-STAT-BASE.4, REQ-CONF.2


def test_req_stat_exp_2_two_runs_on_the_same_input_write_identical_stats_files(tmp_path):
    raw, snap = raw_folder(tmp_path)
    kw = {"raw_dir": raw, "snapshot_md": snap, "run_time": "2026-11-13T00:00:00Z"}
    run_pipeline(out_dir=tmp_path / "o1", work_dir=tmp_path / "d1", **kw)
    run_pipeline(out_dir=tmp_path / "o2", work_dir=tmp_path / "d2", **kw)
    a = {p.name: p.read_bytes() for p in (tmp_path / "o1" / "stats").iterdir()}
    b = {p.name: p.read_bytes() for p in (tmp_path / "o2" / "stats").iterdir()}
    assert a == b and len(a) > 10


def test_req_stat_val_1_the_committed_owner_config_names_four_neighborhoods_that_the_export_uses():
    """REQ-STAT-VAL.1 (ops#101): data/labels/validation_config.json holds the owner's four neighborhoods, seed 311 and n 50,
    each a name the pipeline's neighborhood rule can produce."""
    from pathlib import Path

    from undead311.ingest.neighborhoods import canonical_neighborhood

    cfg = read_config(Path(__file__).resolve().parents[3] / "data" / "labels" / "validation_config.json")
    assert cfg is not None and cfg["seed"] == 311 and cfg["n"] == 50
    assert cfg["neighborhoods"] == sorted(
        ["Fenway / Kenmore / Audubon Circle / Longwood", "Mission Hill", "Roxbury", "South End"]
    )
    assert all(canonical_neighborhood(n) == n for n in cfg["neighborhoods"])


def test_req_stat_placebo_1_a_shift_of_zero_reproduces_the_excess_with_the_same_estimator():
    """REQ-STAT-PLACEBO.1, REQ-STAT-BASE.1 (ops#111, ops#112): the placebo runs the baseline's own season-integrated estimator
    on the moved closures, so a shift of 0 gives observed hits minus the excess's expected. Reports at least 62 days apart, so
    no report opens in a dead stretch (an incident born there leaves out its ancestor in the excess, which the placebo does not)."""
    from undead311.stats.cohort import eligible_originals
    from undead311.stats.shift import _build, _placebo

    rng = np.random.default_rng(7)
    cs = []
    for s in range(30):
        t = 0.0
        for n in range(8):
            cs.append(mk(f"P{s:02d}-{n}", t, t + 2.0, x=s * 1000.0, segment=f"seg{s}"))
            t += 70.0 + rng.exponential(120.0)
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(4000))
    sp = _build(m)
    assert sp is not None and sp.spot_based.any()
    got = _placebo(m, sp, np.zeros((len(sp.keys), 1)), min(float(m.groups[k][0][0]) for k in sp.keys), 311)
    shift, _ = shift_and_placebo(m, 311, 10, 1)
    expected = sum(m.estimate(i).p or 0.0 for i in eligible_originals(res.incidents, m.data_end, m.params)
                   if m._incident_key[i.incident_id] in sp.keys)  # fmt: skip
    assert got is not None and shift is not None
    assert got.excess == pytest.approx(shift.observed - expected, abs=1e-6)


def causal_town(q, bg=300.0, spots=300, span=1400, seed=5):
    """Background reports at Poisson times (a report every `bg` days per spot), each closed 2 days after it opens. After every
    closure a causal re-report follows 5-40 days later with probability q, and it can start a chain itself."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(spots):
        times, t = [], 0.0
        while True:
            t += rng.exponential(bg)
            if t > span:
                break
            times.append(t)
        i = 0
        while i < len(times):
            if rng.random() < q and times[i] + 2.0 + 40.0 < span:
                times.append(times[i] + 2.0 + rng.uniform(5.0, 40.0))
            i += 1
        out += [mk(f"S{s:03d}-{k:03d}", o, o + 2.0, x=s * 1000.0, segment=f"seg{s}") for k, o in enumerate(sorted(times))]
    return out


@pytest.mark.parametrize("q", [0.2, 0.4])
def test_req_stat_base_1_a_causal_resurrection_town_has_an_expected_count_close_to_the_true_chance(q):
    """REQ-STAT-BASE.1, REQ-STAT-BASE.2 (ops#113): real resurrections, and the links of a chain, are not chance reports. 300 spots
    with a background report every 300 days and a causal re-report 5-40 days after each closure with probability q: the true
    chance of a window holding a background report is 1 - exp(-60/300) = 0.181 per original. The expected count ran 1.5 times
    that before the 60 days after a resurrection's own closure were left out as well; it is now within 1.0-1.25."""
    ratios, observed_over_true = [], []
    for seed in (5, 6):
        cs = causal_town(q, seed=seed)
        res = detect(cs)
        m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1400))
        el = list(eligible_originals(res.incidents, m.data_end))
        expected = sum(m.estimate(i).p or 0.0 for i in el)
        true_chance = len(el) * (1.0 - np.exp(-60.0 / 300.0))
        zs = {z.incident_id for z in res.zombies if z.tier == "headline"}
        ratios.append(expected / true_chance)
        observed_over_true.append(sum(i.incident_id in zs for i in el) / true_chance)
    assert all(1.0 <= r <= 1.25 for r in ratios), ratios
    assert all(o > 1.5 for o in observed_over_true)  # the causal re-reports are far above the chance count


def test_req_stat_base_1_a_mixed_gap_null_town_has_an_excess_interval_that_covers_zero():
    """REQ-STAT-BASE.1-2 (ops#114): 300 spots whose reports come every 30, 60, 120, 250 or 400 days, nothing resurrecting by
    cause. Busy and quiet spots together: the excess interval holds 0 in every seeded town (seeds 5-8)."""
    from helpers import mk as _mk

    for seed in (5, 6, 7, 8):
        rng = np.random.default_rng(seed)
        cs = []
        for s in range(300):
            gap = (30.0, 60.0, 120.0, 250.0, 400.0)[int(rng.integers(5))]
            t, n = 0.0, 0
            while True:
                t += rng.exponential(gap)
                if t > 1400:
                    break
                cs.append(_mk(f"S{s:03d}-{n:03d}", t, t + 2.0, x=s * 1000.0, segment=f"seg{s}"))
                n += 1
        res = detect(cs)
        m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1400))
        row = next(r for r in excess_rows(m, 311, 200) if r.kind == "family" and r.tier_set == "headline")
        assert row.lo <= 0 <= row.hi, (seed, row)


def test_req_stat_int_1_a_group_whose_originals_share_one_spot_gets_an_interval_with_width_and_no_placebo_warning():
    """REQ-STAT-INT.1, REQ-STAT-PLACEBO.2 (ops#115): 12 originals at one spot (a report about every 100 days) used to give an
    excess of 0.99 [0.99, 0.99]. With fewer than MIN_CLUSTERS spots the interval is never narrower than the Bernoulli noise
    of the outcomes, and the placebo never warns on so few spots."""
    from undead311.stats.intervals import MIN_CLUSTERS

    cs = [mk(f"A{n:02d}", 100.0 * n, 100.0 * n + 2.0) for n in range(12)]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1400))
    rows = [r for r in excess_rows(m, 311, 200) if r.kind == "family"]
    assert rows and all(r.hi - r.lo > 0.1 for r in rows)
    assert all(r.lo <= r.excess <= r.hi for r in rows)
    _shift, placebo = shift_and_placebo(m, 311, 50, 5)
    assert placebo is not None and placebo.calibration_warning is False and MIN_CLUSTERS >= 2


def test_req_stat_int_1_the_floor_is_the_bernoulli_noise_when_few_spots_and_not_applied_when_many():
    """REQ-STAT-INT.1 (ops#115): `bootstrap_sum_cells` with one cluster holds the +-1.96 sd of sum(p(1-p)); with many clusters
    it is the plain bootstrap."""
    from undead311.stats.intervals import bootstrap_sum_cells

    rng = np.random.default_rng(1)
    vals = [1.0 - 0.5, -0.5, 1.0 - 0.5, -0.5]  # four originals with p = 0.5: two observed, two not
    lo, hi = bootstrap_sum_cells(vals, [-1] * 4, [], [], rng, 200, clusters=[0, 0, 0, 0])
    half = 1.96 * np.sqrt(4 * 0.25)
    assert lo <= -half + 1e-9 and hi >= half - 1e-9  # one spot: the sum of values is 0, the floor gives +-1.96
    many = [0.5, -0.5] * 50
    lo2, hi2 = bootstrap_sum_cells(many, [-1] * 100, [], [], np.random.default_rng(1), 500, clusters=list(range(100)))
    assert hi2 - lo2 < 2 * 1.96 * np.sqrt(100 * 0.25) * 1.2  # a plain bootstrap of 100 clusters, near the Bernoulli width
