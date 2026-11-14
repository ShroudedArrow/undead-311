"""REQ-STAT-BASE.1-4, REQ-STAT-NBR.1-2, REQ-STAT-INT.1: same-spot baseline, neighborhood check and excess, by hand."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest
from helpers import day, mk

from undead311.detect.core import detect
from undead311.detect.params import DEFAULT
from undead311.stats.baseline import DAY, MIN_WINDOWS, BaselineModel, excess_rows, season_array, window_counts
from undead311.stats.pipeline import zombie_baselines

W = 60 * DAY


def ts(d):
    return day(d).timestamp()


def test_req_stat_base_1_window_counts_by_hand():
    """One closure on day 1; reports on days 0, 130 and 250; data end day 400. Windows start on days 60, 120, ... 300."""
    opens = np.array([ts(0), ts(130), ts(250)])
    closes = np.array([ts(1)])
    n, hit = window_counts(opens, closes, ts(400), W)
    # day 60 starts within 60 days after the closure: left out. Day 120 (summer) has the day-130 report, day 180
    # (summer) none, day 240 (autumn) the day-250 report, day 300 (winter) none.
    assert n.tolist() == [1, 0, 2, 1] and hit.tolist() == [0, 0, 1, 1]
    assert season_array(np.array([ts(120), ts(240), ts(300)])).tolist() == [2, 3, 0]


def test_req_stat_base_1_the_first_report_is_never_a_hit_and_closure_adjacent_windows_are_dropped():
    n, hit = window_counts(np.array([ts(0)]), np.array([ts(200)]), ts(400), W)
    assert hit.sum() == 0
    # starts 60, 120, 180, 240, 300: only 240 has the closure inside [start - 60, start] = [180, 240], so 4 remain
    assert n.sum() == 4


def spot_town(report_every=30.0, until=2000):
    """One closed pothole on day 0, then a report every `report_every` days at the same place."""
    out = [mk("A0", 0, 1)]
    d = report_every
    i = 0
    while d < until:
        out.append(mk(f"R{i:03d}", d))
        d += report_every
        i += 1
    return out


def test_req_stat_base_1_p_spot_is_the_share_of_comparable_windows_with_a_report():
    cs = spot_town(30.0)
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(2000))
    inc = next(i for i in res.incidents if i.incident_id == "A0")
    est = m.estimate(inc)
    assert est.source == "spot" and est.windows >= MIN_WINDOWS and est.p == 1.0  # a report every 30 days: every 60-day window has two
    sparse = [mk("A0", 0, 1), mk("Z", 1999)]
    res2 = detect(sparse)
    m2 = BaselineModel({c.id: c for c in sparse}, res2, data_end=day(2000))
    est2 = m2.estimate(next(i for i in res2.incidents if i.incident_id == "A0"))
    assert est2.source == "spot" and est2.p == 0.0 and est2.windows >= MIN_WINDOWS


def test_req_stat_base_3_a_spot_with_few_windows_falls_back_and_the_fallback_is_counted():
    cs = [mk("A0", 0, 1), mk("R1", 10)]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(200))
    inc = res.incidents[0]
    est = m.estimate(inc)
    assert est.windows < MIN_WINDOWS and est.source == "citywide" and est.p is not None  # no neighborhood area: pooled windows
    assert m.fallback_counts(res.incidents) == {"spot": 0, "neighborhood": 0, "citywide": 1, "none": 0}


def test_req_stat_base_3_the_neighborhood_estimate_is_the_first_fallback():
    cs = [mk("A0", 0, 1), mk("R1", 10)]
    cs = [replace(c, neighborhood="Roxbury") for c in cs]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(200), areas_m2={"Roxbury": 1e7})
    est = m.estimate(res.incidents[0])
    assert est.source == "neighborhood" and est.p == est.p_nbr and est.expected_nbr is not None


def test_req_stat_nbr_1_lambda_excludes_reports_near_the_case_and_p_is_one_minus_exp():
    """Reports within RADIUS_M and +-WINDOW_DAYS of the case (and the case itself) do not feed lambda; far ones do."""
    base = [mk("A0", 0, 1)] + [mk(f"F{i}", 5 + i, x=5000.0 + 100 * i) for i in range(10)]  # spring, 5 km away
    near = [mk("N1", 10, x=10.0)]  # 10 m away, 9 days after the closure: excluded
    area = 5e6

    def run(extra):
        cs = [replace(c, neighborhood="Roxbury") for c in base + extra]
        res = detect(cs)
        m = BaselineModel({c.id: c for c in cs}, res, data_end=day(400), areas_m2={"Roxbury": area})
        inc = next(i for i in res.incidents if i.incident_id == "A0")
        return m, m.nbr(inc)

    m, (p0, e0) = run([])
    _m2, (_p1, e1) = run(near)
    assert e0 == pytest.approx(e1) and p0 == pytest.approx(1 - math.exp(-e0))
    lam = 10 / (area * m._season_days[1])  # the 10 far spring reports; A0 itself is inside its own buffer
    assert e0 == pytest.approx(lam * math.pi * 30**2 * 60)


def test_req_stat_nbr_1_no_area_means_no_neighborhood_estimate():
    cs = [mk("A0", 0, 1)]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(200))
    assert m.nbr(res.incidents[0]) is None


def test_req_stat_base_2_excess_is_observed_minus_expected_with_a_seeded_interval():
    cs = spot_town(30.0, 600) + [mk("B0", 0, 1, x=800.0), mk("BR", 10, x=800.0)]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(600))
    rows = excess_rows(m, seed=311, boot=200)
    again = excess_rows(BaselineModel({c.id: c for c in cs}, res, data_end=day(600)), seed=311, boot=200)
    assert rows == again
    fam = next(r for r in rows if r.kind == "family" and r.tier_set == "headline")
    assert fam.observed == sum(1 for z in res.zombies if z.tier == "headline")
    assert fam.excess == pytest.approx(fam.observed - fam.expected)
    assert fam.lo <= fam.hi
    assert {r.kind for r in rows} == {"department", "family", "neighborhood"}
    assert {r.tier_set for r in rows} == {"headline", "all"}


def test_req_stat_base_4_zombie_baselines_covers_every_zombie_with_a_value_in_0_1():
    cs = spot_town(30.0, 600)
    res = detect(cs)
    got = zombie_baselines(None, res, {c.id: c for c in cs}, DEFAULT)
    assert set(got) == {z.zombie_id for z in res.zombies} and all(0.0 <= v <= 1.0 for v in got.values())
