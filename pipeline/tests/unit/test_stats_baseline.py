"""REQ-STAT-BASE.1-4, REQ-STAT-NBR.1-2, REQ-STAT-INT.1: same-spot baseline, neighborhood check and excess, by hand."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest
from helpers import at, day, mk

from undead311.detect.core import detect
from undead311.detect.params import DEFAULT
from undead311.stats.baseline import DAY, MIN_WINDOWS, BaselineModel, excess_rows, season_array, thinned_p
from undead311.stats.cohort import spot_key
from undead311.stats.pipeline import zombie_baselines

W = 60 * DAY


def ts(d):
    return day(d).timestamp()


def test_req_stat_base_1_thinned_p_by_hand():
    """3 other reports in a 240-day season, windows of 60 days: each lands in a given window with probability 1/4."""
    p, windows = thinned_p(3, 240.0, 60.0)
    assert windows == 4 and p == pytest.approx(1 - 0.75**3)
    assert thinned_p(0, 240.0, 60.0) == (0.0, 4)
    assert thinned_p(5, 59.0, 60.0) is None  # less than one window watched
    assert season_array(np.array([ts(120), ts(240), ts(300)])).tolist() == [2, 3, 0]


def test_req_stat_base_1_live_time_leaves_out_the_window_days_after_each_closure_and_the_reports_in_them():
    """First report day 0, one closure on day 1, reports on days 10, 20 and 130, data end day 400. The 60 days after the closure
    (day 1 to 61) are dead: the reports on days 10 and 20 are in them, so only the day-130 report is a live chance report."""
    cs = [mk("A0", 0, 1), mk("R1", 10), mk("R2", 20), mk("R3", 130)]
    m = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(400))
    opens = np.array([ts(0), ts(10), ts(20), ts(130)])
    live = m.live_spot(opens, np.array([ts(1)]))
    assert live.span.tolist() == [90.0, 127.0, 92.0, 91.0]  # winter, spring, summer, autumn: 2024-03-04 .. 2025-04-07
    assert live.days.tolist() == [90.0, 127.0 - 60.0, 92.0, 91.0]  # 60 spring days are dead
    assert live.counts.tolist() == [0, 0, 1, 0]  # day 130 is 2024-07-12, a summer day
    assert live.is_live(np.array([ts(0.5), ts(1), ts(30), ts(61), ts(62)])).tolist() == [True, True, False, False, True]


def test_req_stat_base_1_overlapping_stretches_are_merged_and_a_report_in_a_dead_stretch_starts_none():
    """A closure on day 1 and another on day 10 make one dead stretch, day 1 to 70. A report opened on day 5 is dead, so its
    own closure on day 6 starts no stretch of its own (REQ-STAT-BASE.1)."""
    cs = [mk("A0", 0, 1), mk("D", 5, 6), mk("E", 8, 10)]
    m = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(400))
    _opens, closes, live_closes = m.groups[next(iter(m.groups))]
    assert closes.tolist() == [ts(1), ts(6), ts(10)] and live_closes.tolist() == [ts(1)]
    live = m.live_spot(np.array([ts(0), ts(5), ts(8)]), np.array([ts(1), ts(10)]))
    assert (live.dead_s.tolist(), live.dead_e.tolist()) == ([ts(1)], [ts(70)])


def test_req_stat_base_1_own_members_are_not_chance_reports_and_a_resurrection_leaves_out_its_ancestor():
    """Live-born incident: its own live members are left out. Born in a dead stretch: the live report that started the stretch is."""
    cs = [mk("F", 0), mk("L1", 10, 11), mk("L1b", 10.5, 12), mk("R", 20, 21)]  # F is the first report; L1 and L1b are one incident
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(400))
    by_member = {mid: i for i in res.incidents for mid in i.member_ids}
    assert m.own_after(by_member["L1"]).tolist() == [0, 2, 0, 0]  # two live members, both spring
    assert m.own_after(by_member["R"]).tolist() == [0, 1, 0, 0]  # R is dead (day 12 to 72); the live report before it is L1b
    live = m._spot_info[next(iter(m.groups))]
    assert live.counts.tolist() == [0, 2, 0, 0]  # L1 and L1b; F is the first report and R is dead
    p, windows = m.spot_p(by_member["L1"], 1)
    assert p == 0.0 and windows == 2  # no other live report in spring, and 127 spring days hold two windows


def test_req_stat_base_1_the_first_report_is_never_a_chance_report():
    cs = [mk("A0", 0, 1)]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(400))
    assert m.spot_p(res.incidents[0], 1)[0] == 0.0


def test_req_stat_base_1_a_mirror_copy_is_not_a_second_report():
    cs = [mk("A0", 0, 1), mk("A0M", 0, system="new", open_hours=2.0), mk("R1", 130, 131), mk("Q", 140, 141, x=900.0)]
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(400))
    assert "A0M" in res.mirror_ids
    live = m._spot_info[("pothole_roadway", spot_key(None, *at(0.0)[:2], DEFAULT))]
    assert live.counts.sum() == 1  # R1; the mirror copy is the same report as A0


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
    assert est.source == "spot" and est.windows >= MIN_WINDOWS and est.p > 0.8  # a report every 30 days: two per window, 1 - e^-2 = 0.86
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
