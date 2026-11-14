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
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(700))
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
