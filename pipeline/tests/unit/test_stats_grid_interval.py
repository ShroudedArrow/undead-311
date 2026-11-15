"""REQ-STAT-GRID.1, REQ-STAT-INT.1-2, REQ-STAT-EXP.2 (ops#182): every sensitivity-grid point carries an interval for its excess and
for its stayed-fixed rate."""

from __future__ import annotations

from dataclasses import replace

import duckdb
from helpers import mk

from undead311.detect.grid import run_grid, store_grid
from undead311.detect.params import DEFAULT
from undead311.export.writers import validate
from undead311.stats.gridstats import GridMetrics, grid_payload, store_grid_metrics


def grid_payload_of(cs):
    con = duckdb.connect()
    metrics = GridMetrics()
    store_grid(con, run_grid(con, cs, observer=metrics))
    store_grid_metrics(con, metrics)
    return grid_payload(con, "v", DEFAULT, "sample"), metrics


def town():
    """Originals 200 m apart, half of them re-reported, a spread of on-time flags."""
    cs = []
    for i in range(24):
        cs.append(replace(mk(f"A{i}", 0, 2, x=i * 200.0), on_time=i % 3 != 0))
        if i % 2 == 0:
            cs.append(mk(f"R{i}", 12, x=i * 200.0))
    cs.append(mk("LATE", 400, x=9000.0))
    return cs


def test_req_stat_grid_1_every_point_has_an_interval_for_the_excess_and_the_stayed_fixed_rate():
    payload, _metrics = grid_payload_of(town())
    validate("sensitivity_grid", payload)
    assert len(payload["points"]) == 18
    for p in payload["points"]:
        assert p["excess_lo"] <= p["excess"] <= p["excess_hi"], p
        assert 0 <= p["stayed_fixed_lo"] <= p["stayed_fixed_rate"] <= p["stayed_fixed_hi"] <= 1, p


def test_req_stat_grid_1_the_stayed_fixed_interval_is_the_wilson_interval_of_the_scorecard():
    """By hand for the default point (segment matching, 30 m, 60 days): 16 of the 24 originals are on time (not i % 3 == 0);
    the stayed-fixed rate and its interval are those of `stats.rates.scorecards`."""
    from undead311.detect.core import detect
    from undead311.stats.intervals import make_rate
    from undead311.stats.rates import CITYWIDE, scorecards

    cs = town()
    payload, _ = grid_payload_of(cs)
    point = next(p for p in payload["points"] if (p["matching"], p["radius_m"], p["window_days"]) == ("segment", 30, 60))
    end = max(c.open_utc for c in cs)
    card = next(c for c in scorecards(detect(cs), {c.id: c for c in cs}, end) if c.family == CITYWIDE and c.tier_set == "headline")
    assert (point["stayed_fixed_rate"], point["stayed_fixed_lo"], point["stayed_fixed_hi"]) == (
        card.stayed_fixed_raw.rate, card.stayed_fixed_raw.lo, card.stayed_fixed_raw.hi)
    assert card.stayed_fixed_raw.rate == make_rate(card.stayed_fixed_raw.k, card.stayed_fixed_raw.n).rate


def test_req_stat_exp_2_the_grid_intervals_are_the_same_on_a_rerun_and_for_any_input_order():
    a, _ = grid_payload_of(town())
    b, _ = grid_payload_of(list(reversed(town())))
    assert a == b


def test_req_stat_grid_1_a_run_with_nothing_to_estimate_has_null_intervals_and_the_schema_accepts_them():
    payload, _ = grid_payload_of([mk("ONLY", 0, 2)])
    validate("sensitivity_grid", payload)
    for p in payload["points"]:
        if p["excess"] is None:
            assert p["excess_lo"] is None and p["excess_hi"] is None


def test_req_stat_grid_1_the_schema_accepts_an_old_file_without_the_interval_fields():
    payload, _ = grid_payload_of(town())
    for p in payload["points"]:
        for key in ("excess_lo", "excess_hi", "stayed_fixed_lo", "stayed_fixed_hi"):
            del p[key]
    validate("sensitivity_grid", payload)

