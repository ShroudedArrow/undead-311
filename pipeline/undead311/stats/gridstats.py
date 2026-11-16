"""Sensitivity grid file (REQ-STAT-GRID.1, REQ-SENS-RUN).

The engine's grid runs (`detect.grid.run_grid`) give zombie counts per tier. For the two numbers a count cannot give, the
stats stage observes each run as it is made: `GridMetrics` computes the headline excess (observed minus the same-spot
baseline, over the run's eligible originals) and the citywide raw stayed-fixed rate, and `store_grid_metrics` writes them to
the DuckDB table `grid_metrics` (the two numbers and the 95% interval of each, ops#182: a 200-replicate seeded cluster bootstrap for the excess,
the Wilson interval for the stayed-fixed rate). `grid_payload` joins that table with `grid_run_index`.
Matching, radius and window enter each run through its own parameters (including the 60 m cell of unsnapped cases).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import duckdb
import numpy as np

from undead311.detect.grid import run_id
from undead311.detect.model import Case, DetectionResult
from undead311.detect.params import Params
from undead311.stats.baseline import BaselineModel, excess_interval
from undead311.stats.cohort import eligible_originals
from undead311.stats.meta import params_json
from undead311.stats.rates import CITYWIDE, scorecards

GRID_BOOT = 200  # bootstrap replicates for the interval of one grid point's excess (REQ-STAT-GRID.1, ops#182); 1,000 per point is too slow
GRID_SEED = 311  # every grid point draws from a fresh generator with this seed (REQ-STAT-EXP.2)


def headline_excess_interval(model: BaselineModel, boot: int = GRID_BOOT) -> tuple[float, float] | None:
    """Seeded bootstrap 95% interval of `headline_excess` (REQ-STAT-GRID.1, REQ-STAT-INT.1): the same cohort and the same
    cluster bootstrap as the excess rows, with `boot` replicates; None without any original that has a baseline."""
    zs = {z.incident_id for z in model.result.zombies if z.tier == "headline"}
    vals = []
    for inc in model.excess_cohort("headline"):
        est = model.estimate(inc)
        vals.append((1.0 if inc.incident_id in zs else 0.0, est.p, est.expected_nbr, est.source != "spot", est.cell, est.n_eff,
                     est.cluster, model.is_bursty(inc)))  # fmt: skip
    if not vals:
        return None
    return excess_interval(vals, np.random.Generator(np.random.PCG64(GRID_SEED)), boot)


def headline_excess(model: BaselineModel) -> float | None:
    """Observed minus expected over the eligible headline originals that have a baseline; None without any."""
    zs = {z.incident_id for z in model.result.zombies if z.tier == "headline"}
    total, seen = 0.0, 0
    for inc in eligible_originals(model.result.incidents, model.data_end, model.params):
        p = model.p(inc)
        if p is None:
            continue
        total += (1.0 if inc.incident_id in zs else 0.0) - p
        seen += 1
    return total if seen else None


class GridMetrics:
    """An observer for `run_grid`: excess and stayed-fixed rate per run (REQ-STAT-GRID.1)."""

    def __init__(self, areas_m2: Mapping[str, float] | None = None) -> None:
        self.areas_m2 = dict(areas_m2 or {})
        # run id -> (excess, stayed-fixed rate, excess lo, excess hi, stayed-fixed lo, stayed-fixed hi)
        self.rows: dict[str, tuple[float | None, ...]] = {}

    def __call__(self, p: Params, cases: list[Case], result: DetectionResult, without: bool) -> None:
        if not cases:
            self.rows[run_id(p, without)] = (None,) * 6
            return
        by_id = {c.id: c for c in cases}
        end = max(c.open_utc for c in cases)
        model = BaselineModel(by_id, result, p, end, self.areas_m2)
        card = next(c for c in scorecards(result, by_id, end, p) if c.family == CITYWIDE and c.tier_set == "headline")
        ci = headline_excess_interval(model)
        sf = card.stayed_fixed_raw
        self.rows[run_id(p, without)] = (headline_excess(model), sf.rate, *(ci or (None, None)), sf.lo, sf.hi)


def store_grid_metrics(con: Any, metrics: GridMetrics) -> None:
    con.execute("drop table if exists grid_metrics")
    con.execute(
        "create table grid_metrics(run_id varchar, excess double, stayed_fixed_rate double, excess_lo double, excess_hi double, "
        "stayed_fixed_lo double, stayed_fixed_hi double)"
    )
    if metrics.rows:
        con.executemany("insert into grid_metrics values (?,?,?,?,?,?,?)", [(k, *v) for k, v in sorted(metrics.rows.items())])


def grid_payload(con: Any, data_version: str, params: Params, dataset: str) -> dict | None:
    """`sensitivity_grid.json` from `grid_run_index` and `grid_metrics`; None when the grid was not run."""
    try:
        runs = con.execute(
            "select i.run_id, i.matching, i.radius_m, i.window_days, i.without_street_light_other, i.headline, "
            "i.source_unknown, i.city_rereport, i.sensitivity, m.excess, m.stayed_fixed_rate, m.excess_lo, m.excess_hi, "
            "m.stayed_fixed_lo, m.stayed_fixed_hi from grid_run_index i "
            "left join grid_metrics m using (run_id) order by i.run_id"
        ).fetchall()
    except duckdb.Error:  # no grid tables: the run skipped the grid
        return None
    points, without = [], {"headline": 0, "all_tiers": 0}
    for _rid, matching, radius, window, no_slo, head, su, city, sens, excess, stayed, e_lo, e_hi, s_lo, s_hi in runs:
        if no_slo:
            without = {"headline": int(head), "all_tiers": int(head + su + city + sens)}
            continue
        points.append({
            "matching": matching, "radius_m": int(radius), "window_days": int(window), "headline": int(head),
            "source_unknown": int(su), "city_rereport": int(city), "sensitivity": int(sens), "excess": excess, "stayed_fixed_rate": stayed,
            "excess_lo": e_lo, "excess_hi": e_hi, "stayed_fixed_lo": s_lo, "stayed_fixed_hi": s_hi,
        })  # fmt: skip
    return {
        "data_version": data_version, "dataset": dataset, "params": params_json(params), "seed": None,
        "points": points, "without_street_light_other": without,
    }  # fmt: skip
