"""Hybrid same-spot baseline (REQ-STAT-BASE.1-2, REQ-STAT-PLACEBO.1; ops#130, ops#131, ops#132).

Sparse spots use the season-integrated thinned count; dense spots (at least one report per two windows) use the share of
sliding windows that hold a report. The acceptance in methods.md: in seeded null towns (nothing resurrects by cause) the excess
interval never lies above 0; below 0 is allowed and documented in docs/METHODS.md."""

from __future__ import annotations

import numpy as np
import pytest
from helpers import day, mk

from undead311.detect.core import detect
from undead311.stats.baseline import BaselineModel, excess_rows, season_array
from undead311.stats.cohort import eligible_originals
from undead311.stats.shift import _build, _placebo, shift_and_placebo

END = 1400


def town(gaps, seed, spots=300, span=END, season_mult=None):
    """Poisson reports at every spot with a mean gap drawn from `gaps` (one value: all spots), each closed 2 days after it
    opens; `season_mult` (winter, spring, summer, autumn) thins the reports by season."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(spots):
        gap = gaps[0] if len(gaps) == 1 else gaps[int(rng.integers(len(gaps)))]
        t, n = 0.0, 0
        top = max(season_mult) if season_mult else 1.0
        while True:
            t += rng.exponential(gap / top)
            if t > span:
                break
            if season_mult:
                sea = int(season_array(np.array([day(t).timestamp()]))[0])
                if rng.random() > season_mult[sea] / top:
                    continue
            out.append(mk(f"S{s:03d}-{n:03d}", t, t + 2.0, x=s * 1000.0, segment=f"seg{s}"))
            n += 1
    return out


def headline_excess(cs, boot=200):
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(END))
    row = next(r for r in excess_rows(m, 311, boot) if r.kind == "family" and r.tier_set == "headline")
    return m, row


def test_req_stat_base_1_a_spot_with_a_report_every_two_windows_is_dense_and_one_with_fewer_is_sparse():
    """REQ-STAT-BASE.1 (ops#131): the class depends on the reports and the watched span only (one per DENSE_WINDOWS x
    WINDOW_DAYS = 120 days)."""
    dense = [mk(f"D{n}", 100.0 * n, 100.0 * n + 2.0, x=0.0, segment="d") for n in range(14)]  # one per 100 days
    sparse = [mk(f"P{n}", 150.0 * n, 150.0 * n + 2.0, x=900.0, segment="p") for n in range(10)]  # one per 150 days
    cs = dense + sparse
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(1400))
    key = {c.id: m._incident_key[next(i.incident_id for i in res.incidents if c.id in i.member_ids)] for c in (cs[0], cs[-1])}
    assert m.is_dense(key["D0"]) and not m.is_dense(key["P9"])


def test_req_stat_base_1_the_dense_share_counts_sliding_windows_that_hold_a_report_by_hand():
    """REQ-STAT-BASE.1 (ops#131): reports on days 0, 100 and 300, each closed a day later, data ends day 400. Window starts are
    the whole days 0..340 outside the 60 days after each closure; a start t counts when a report opens in (t, t + 60]."""
    cs = [mk("A", 0, 1), mk("B", 100, 101), mk("C", 300, 301)]
    m = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(400))
    opens, closes = np.array([day(0).timestamp(), day(100).timestamp(), day(300).timestamp()]), np.array(
        [day(1).timestamp(), day(101).timestamp(), day(301).timestamp()]
    )
    live = m.live_spot(opens, closes)
    share = m.dense_share(opens, live)
    starts = np.arange(0, 341)
    dead = ((starts > 1) & (starts <= 61)) | ((starts > 101) & (starts <= 161)) | ((starts > 301) & (starts <= 361))
    ok = starts[~dead]
    hit = [(any(t < d <= t + 60 for d in (0, 100, 300))) for t in ok]
    assert share[4] == pytest.approx(np.mean(hit)) and 0.0 < share[4] < 1.0
    assert np.isnan(share[:4]).sum() < 4  # seasons that hold a start have a share, others are nan


@pytest.mark.parametrize("seed", [5, 6, 7, 8])
def test_req_stat_base_2_a_near_regular_30_day_null_town_has_an_excess_interval_never_above_zero(seed):
    """REQ-STAT-BASE.1-2 (ops#130, ops#131): 300 spots with a report every 30 days, 1,400 days, seeds 5-8. The pooled p of the
    old estimator ran low and gave +693 to +1,075 with an interval above 0; the dense share puts the excess below 0."""
    _m, row = headline_excess(town((30.0,), seed))
    assert row.lo <= 0 and row.excess <= 0, row


@pytest.mark.parametrize("seed", [5, 6, 7, 8, 9, 10])
def test_req_stat_base_2_the_mixed_30_and_60_day_null_towns_have_an_excess_interval_never_above_zero(seed):
    """REQ-STAT-BASE.1-2 (ops#114, ops#131): each spot reported about every 30 or every 60 days; seeds 5-10 (above 0 in 4 of 6
    before the hybrid)."""
    _m, row = headline_excess(town((30.0, 60.0), seed))
    assert row.lo <= 0, row


@pytest.mark.parametrize("gap", [45.0, 60.0])
def test_req_stat_base_2_dense_null_towns_at_45_and_60_days_stay_below_zero(gap):
    """REQ-STAT-BASE.2 (ops#131): the gaps that already held below 0 still do (seeds 5-6)."""
    for seed in (5, 6):
        _m, row = headline_excess(town((gap,), seed))
        assert row.lo <= 0, (gap, seed, row)


@pytest.mark.parametrize("seed", [5, 6, 7, 8])
def test_req_stat_base_2_a_sparse_random_null_town_has_an_excess_interval_never_above_zero(seed):
    """REQ-STAT-BASE.2 (ops#131): 300 spots with a report every 300 days, nothing resurrecting by cause: sparse spots keep the
    season-integrated estimator and an interval that covers 0."""
    _m, row = headline_excess(town((300.0,), seed))
    assert row.lo <= 0 <= row.hi or row.hi < 0, row
    assert row.lo <= 0


@pytest.mark.parametrize("gap", [60.0, 200.0, 400.0])
def test_req_stat_base_2_a_seasonal_null_town_has_an_excess_interval_never_above_zero(gap):
    """REQ-STAT-BASE.2 (ops#131): winter 2x, spring and autumn 1x, summer a quarter of the rate; nothing resurrects by cause
    (seeds 5-6)."""
    for seed in (5, 6):
        _m, row = headline_excess(town((gap,), seed, season_mult=(2.0, 1.0, 0.25, 1.0)))
        assert row.lo <= 0, (gap, seed, row)


def test_req_stat_base_2_the_mixed_30_to_400_day_null_towns_have_an_excess_interval_never_above_zero():
    """REQ-STAT-BASE.2 (ops#114, ops#131): gaps 30, 60, 120, 250 or 400 days drawn per spot, seeds 5-12."""
    for seed in range(5, 13):
        gaps = (30.0, 60.0, 120.0, 250.0, 400.0)
        _m, row = headline_excess(town(gaps, seed))
        assert row.lo <= 0, (seed, row)


def test_req_stat_placebo_1_the_placebo_uses_the_dense_estimator_so_an_unshifted_run_equals_the_excess_baseline():
    """REQ-STAT-PLACEBO.1 (ops#131): with no shift the placebo's expected count is the model's own, dense spots included, so
    placebo excess = candidate hits - sum of the model's p over the same originals."""
    cs = town((60.0,), 5, spots=40, span=700)
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(800))  # no closure in the last window: a shift of 0 wraps none
    sp = _build(m)
    assert sp is not None and any(m.is_dense(k) for k in sp.keys)
    got = _placebo(m, sp, np.zeros((len(sp.keys), 1)), min(float(m.groups[k][0][0]) for k in sp.keys), 311)
    shift, _ = shift_and_placebo(m, 311, 10, 1)
    expected = sum(m.estimate(i).p or 0.0 for i in eligible_originals(res.incidents, m.data_end, m.params)
                   if m._incident_key[i.incident_id] in sp.keys)  # fmt: skip
    assert got is not None and shift is not None
    assert got.excess == pytest.approx(shift.observed - expected, abs=1e-6)


@pytest.mark.parametrize("gap", [30.0, 60.0])
def test_req_stat_placebo_2_a_dense_null_town_placebo_is_never_above_zero(gap):
    """REQ-STAT-PLACEBO.1-2 (ops#131): the placebo on dense null towns lies at or below 0 (cautious), never above."""
    for seed in (5, 6):
        cs = town((gap,), seed)
        res = detect(cs)
        m = BaselineModel({c.id: c for c in cs}, res, data_end=day(END))
        _s, placebo = shift_and_placebo(m, 311, 50, 10)
        assert placebo is not None and placebo.lo <= 0, (gap, seed, placebo)


def test_req_stat_int_1_independent_units_count_a_pooled_cell_once_and_a_spot_once():
    """REQ-STAT-INT.1 (ops#133): originals that share a pooled estimate are one unit, as METHODS.md says, not one each."""
    from undead311.stats.intervals import independent_units

    clusters = [0, 0, 1, -1, -1, -1, -1]
    cells = [-1, -1, -1, 0, 0, 1, -1]  # two spots, a pooled cell of two, another pooled cell, one original with neither
    assert independent_units(clusters, cells) == 2 + 2 + 1


def test_req_stat_int_1_and_placebo_1_the_floor_reads_a_fractional_value_by_its_own_variance():
    """REQ-STAT-INT.1, REQ-STAT-PLACEBO.1 (ops#133): a value that is the mean of 10 outcomes (hit share 0.5, p 0.4, so
    0.1) is read as p = 0.9 without `var` (variance 0.09 each, too wide); with the right variance p(1 - p) / 10 = 0.024 the
    floor is 1.96 * sqrt(sum var)."""
    from undead311.stats.intervals import bootstrap_sum_cells

    vals = [0.1, 0.1, 0.1]
    rng = np.random.Generator(np.random.PCG64(1))
    lo, hi = bootstrap_sum_cells(vals, [-1] * 3, [], [], rng, 200, clusters=[0, 1, 2], var=[0.024] * 3)  # type: ignore[arg-type]
    half = 1.96 * np.sqrt(3 * 0.024)
    assert lo <= 0.3 - half + 1e-9 and hi >= 0.3 + half - 1e-9
    wrong_lo, wrong_hi = bootstrap_sum_cells(vals, [-1] * 3, [], [], np.random.Generator(np.random.PCG64(1)), 200, clusters=[0, 1, 2])  # type: ignore[arg-type]
    assert (wrong_hi - wrong_lo) > (hi - lo)  # p read as 0.9 gives variance 0.09 each: 0.27 against 0.072


def test_req_stat_placebo_2_the_warning_is_set_exactly_when_the_interval_excludes_zero_given_enough_independent_spots():
    """REQ-STAT-PLACEBO.2 (ops#133): 300 independent spots (a report every 60 days, seed 5): the flag equals "the interval
    excludes 0" and, on this null town, the interval is below 0 (cautious)."""
    cs = town((60.0,), 5)
    m = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(END))
    _s, p = shift_and_placebo(m, 311, 50, 10)
    assert p is not None and p.lo <= p.excess <= p.hi
    assert p.calibration_warning == (p.lo > 0 or p.hi < 0) and p.hi < 0


# --- staggered first reports and the dense fallback (REQ-STAT-BASE.1-3, REQ-STAT-PLACEBO.1; ops#136, ops#137) ----------------
def spread_town(kind, seed, spots=300, starts=1300.0):
    """Every spot's first report falls at a random day in [0, starts], so most spots are watched for less than MIN_WINDOWS
    windows of a season and take the fallback. `kind`: ("regular", gap, jitter) reports `gap` +- `jitter` days apart,
    ("poisson", gap...) one mean gap per spot drawn from the list, ("mixreg",) 10% of spots regular every 30 +- 3 days and the
    rest Poisson every 300 days. Each report is closed 2 days after it opens, so nothing resurrects by cause."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(spots):
        t = rng.uniform(0.0, starts)
        mode, gap = kind[0], 300.0
        if mode == "poisson":
            gap = kind[1:][int(rng.integers(len(kind) - 1))]
        elif mode == "mixreg":
            mode, gap = ("regular", 30.0) if rng.random() < 0.1 else ("poisson", 300.0)
        elif mode == "regular":
            gap = kind[1]
        n = 0
        while t <= END:
            out.append(mk(f"S{s:03d}-{n:03d}", t, t + 2.0, x=s * 1000.0, segment=f"seg{s}"))
            n += 1
            t += gap + rng.uniform(-3.0, 3.0) if mode == "regular" else rng.exponential(gap)
    return out


def with_areas(cs, area_m2):
    from dataclasses import replace

    return [replace(c, neighborhood="Roxbury") for c in cs], {"Roxbury": area_m2}


def staggered_excess(cs, areas=None, boot=200):
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(END), areas_m2=areas)
    row = next(r for r in excess_rows(m, 311, boot) if r.kind == "family" and r.tier_set == "headline")
    return m, res, row


@pytest.mark.parametrize("starts", [600.0, 1300.0])
@pytest.mark.parametrize("seed", [5, 6, 7, 8])
@pytest.mark.parametrize("area", [None, 3e6])
def test_req_stat_base_2_a_near_regular_30_day_town_with_staggered_first_reports_is_never_above_zero(seed, area, starts):
    """REQ-STAT-BASE.1-3 (ops#131, ops#136): reports every 30 +- 3 days at 300 spots whose first report falls anywhere in the
    first 600 or 1,300 days, with and without a neighborhood area. Most spots are watched for less than MIN_WINDOWS windows. The
    Poisson fallback gave +1,978 to +3,259 with an interval above 0 (every report of such a spot lands in a dead stretch, so its
    live rate is about 0); a dense spot now reads its own windows however short."""
    cs = spread_town(("regular", 30.0, 3.0), seed, starts=starts)
    areas = None
    if area:
        cs, areas = with_areas(cs, area)
    _m, _res, row = staggered_excess(cs, areas)
    assert row.lo <= 0 and row.excess <= 0, row
    assert row.n_fallback < 0.02 * row.n_originals  # the dense estimate carries them, not a pooled rate


@pytest.mark.parametrize("seed", [5, 6, 7, 8])
@pytest.mark.parametrize("area", [None, 3e6])
def test_req_stat_base_2_the_mixed_null_towns_with_staggered_first_reports_are_never_above_zero(seed, area):
    """REQ-STAT-BASE.1-3 (ops#114, ops#136): the ops#114 mixed town (30 or 60 days), the mixed 30-400 town and 10% near-regular
    spots among Poisson 300-day ones, each with staggered first reports (above 0 in 4 of 4 seeds before: +177 to +261)."""
    for kind in (("poisson", 30.0, 60.0), ("poisson", 30.0, 60.0, 120.0, 250.0, 400.0), ("mixreg",)):
        cs = spread_town(kind, seed)
        areas = None
        if area:
            cs, areas = with_areas(cs, area)
        _m, _res, row = staggered_excess(cs, areas)
        assert row.lo <= 0, (kind, seed, area, row)


@pytest.mark.parametrize("seed", [5, 6, 7, 8])
def test_req_stat_base_2_sparse_random_spots_with_staggered_first_reports_and_a_neighborhood_area_are_never_above_zero(seed):
    """REQ-STAT-BASE.3 (ops#136): the neighborhood rate is the chance at a random point, so on its own it ran low for a spot
    that has reports (+48 to +84, interval above 0, on a sparse town with staggered starts). The fallback is the higher of the
    neighborhood and the pooled family rate."""
    cs, areas = with_areas(spread_town(("poisson", 300.0), seed), 3e7)
    _m, _res, row = staggered_excess(cs, areas)
    assert row.lo <= 0, row


@pytest.mark.parametrize("seed", [5, 6])
def test_req_stat_placebo_2_a_near_regular_town_with_staggered_first_reports_has_a_placebo_never_above_zero(seed):
    """REQ-STAT-PLACEBO.1-2 (ops#136): the placebo reads dense spots with the same windows, however short the spot, so on
    staggered near-regular and mixed null towns it is never above 0 (it was +3,249 and warned)."""
    for kind in (("regular", 30.0, 3.0), ("poisson", 30.0, 60.0, 120.0, 250.0, 400.0)):
        cs = spread_town(kind, seed)
        res = detect(cs)
        m = BaselineModel({c.id: c for c in cs}, res, data_end=day(END))
        _s, placebo = shift_and_placebo(m, 311, 50, 10)
        assert placebo is not None and placebo.lo <= 0, (kind, seed, placebo)


def _estimates(cs, **kw):
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(kw.pop("end", 400)), **kw)
    return m, {i.incident_id: m.estimate(i) for i in res.incidents}, res


def test_req_stat_base_3_a_dense_spot_watched_for_a_short_time_is_read_by_its_own_windows():
    """REQ-STAT-BASE.1, REQ-STAT-BASE.3 (ops#136): a spot reported every 30 days for 150 days has less than MIN_WINDOWS windows in
    any season, yet it is dense with one report per window, so its estimate is the spot's own sliding-window share (here 1:
    every window holds a report) with source "spot", not a pooled rate."""
    cs = [mk(f"A{n}", 30.0 * n, 30.0 * n + 2.0, x=0.0, segment="a") for n in range(6)]
    _m, est, res = _estimates(cs, end=300)
    first = next(i for i in res.incidents if "A0" in i.member_ids)
    e = est[first.incident_id]
    assert e.windows < 4 and e.source == "spot" and e.p == pytest.approx(1.0) and e.cluster is not None


def test_req_stat_base_3_a_short_spot_with_fewer_than_one_report_per_window_keeps_the_pooled_fallback():
    """REQ-STAT-BASE.3 (ops#136): reports 100 days apart are dense by the long-spot rule (one per 120 days) but too few in a short
    span to tell from a lucky sparse spot (it would raise the baseline of sparse towns): the pooled rate is used."""
    cs = [mk(f"A{n}", 100.0 * n, 100.0 * n + 2.0, x=0.0, segment="a") for n in range(4)]
    m, est, res = _estimates(cs, end=330)
    key = m._incident_key[res.incidents[0].incident_id]
    assert m.is_dense(key)
    assert all(e.source == "citywide" for e in est.values())


def test_req_stat_base_3_the_fallback_is_the_higher_of_the_neighborhood_and_the_pooled_rate():
    """REQ-STAT-BASE.3 (ops#136): a neighborhood so large that its rate is almost 0 no longer sets the baseline of a spot whose
    family has live reports; a tiny area (a high rate) still does."""
    from dataclasses import replace

    pool = [mk(f"P{s}-{n}", 10.0 * n + s, 10.0 * n + s + 1.0, x=s * 1000.0, segment=f"p{s}") for s in range(12) for n in range(40)]
    short = [mk("A0", 300.0, 301.0, x=50000.0, segment="z"), mk("A1", 380.0, x=50000.0, segment="z")]  # one report in 140 days: sparse
    cs = [replace(c, neighborhood="Roxbury") for c in pool + short]
    big = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(440), areas_m2={"Roxbury": 1e12})
    inc = next(i for i in big.result.incidents if "A0" in i.member_ids)
    e = big.estimate(inc)
    assert e.p_nbr is not None and e.p_nbr < 1e-3
    assert e.source == "citywide" and e.p > e.p_nbr
    small = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(440), areas_m2={"Roxbury": 1e3})
    e2 = small.estimate(next(i for i in small.result.incidents if "A0" in i.member_ids))
    assert e2.source == "neighborhood" and e2.p == e2.p_nbr
