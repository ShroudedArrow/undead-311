"""Stats stage called by the engine pipeline after detection (design "Run order"). REQ-STAT-EXP.1.

Two entry points:

* `zombie_baselines(con, result, cases, params)`: the same-spot baseline per zombie, called before the engine rescores
  confidence (REQ-STAT-BASE.4). The model it builds is kept and reused by `run_stats`.
* `run_stats(...)`: builds every stats payload, validates each against its schema before anything is written, then writes
  `<out>/stats/*.json` and `stats_status.json` (the engine folds it into `status.json`). A file whose inputs are missing
  (no grid, no cases) is not written, and one an earlier run left behind is removed.

Every payload carries `data_version`, `dataset`, `params` and `seed` (null when nothing is resampled). One seed (default
311) drives every resampling step, so a rerun on the same input is byte-identical (REQ-STAT-EXP.2).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from undead311.detect.core import detect
from undead311.detect.edges import sql_edges
from undead311.detect.model import Case, DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.export.writers import canonical_json, validate, write_text_atomic
from undead311.stats.baseline import BaselineModel
from undead311.stats.city import city_counts, city_only_incidents
from undead311.stats.gridstats import GridMetrics, grid_payload, store_grid_metrics
from undead311.stats.groups import groups_payload, intensity_by_neighborhood
from undead311.stats.meta import params_json
from undead311.stats.rates import counts_by_tier, scorecard_payload, scorecards
from undead311.stats.shift import shift_and_placebo
from undead311.stats.survival import horizon_params, survival_payload
from undead311.stats.temporary import temporary_payload
from undead311.stats.tiers import (
    TierBaselines,
    TierModel,
    band_excess_rows,
    mode_counts,
    tier_excess_rows,
    tier_models,
)
from undead311.stats.tour import build_tour, read_override
from undead311.stats.trend import trend_payload
from undead311.stats.validation import LABELS_FILE, SAMPLE_FILE, read_labels, read_sample_ids, score

OVERRIDE_FILE = "judge_tour_override.json"
SEED = 311
__all__ = ["GridMetrics", "run_stats", "store_grid_metrics", "zombie_baselines"]
STAT_FILES = (
    "scorecard.json", "judge_tour.json", "excess.json", "survival.json", "funnel.json", "groups.json",
    "sensitivity_grid.json", "temporary_fixes.json", "validation.json", "trends.json",
)  # fmt: skip

_MODEL: dict[str, Any] = {}
_TIERS: dict[str, Any] = {}


def neighborhood_geometry(con: Any) -> tuple[dict[str, float], dict[str, float]]:
    """(area in m2, street km) by neighborhood from the `neighborhood_areas` table; empty without it (REQ-STAT-NBR.2)."""
    try:
        rows = con.execute("select name, area_m2, street_km from neighborhood_areas").fetchall()
    except duckdb.Error:  # no table: the run had no boundaries
        return {}, {}
    return {n: a for n, a, _ in rows if a}, {n: k for n, _a, k in rows if k}


def get_model(
    con: Any, result: DetectionResult, cases: Mapping[str, Case], params: Params, data_end: datetime | None = None
) -> BaselineModel:
    """The baseline model of this detection result; built once and reused (`zombie_baselines` then `run_stats`)."""
    end = data_end or max((c.open_utc for c in cases.values()), default=None)
    if _MODEL.get("result") is result and _MODEL.get("cases") is cases and _MODEL.get("key") == (params, end):
        return _MODEL["model"]
    areas, _km = neighborhood_geometry(con) if con is not None else ({}, {})
    model = BaselineModel(cases, result, params, end, areas)
    _MODEL.clear()
    _MODEL.update(result=result, cases=cases, key=(params, end), model=model)
    return model


def get_tier_models(
    con: Any, result: DetectionResult, cases: Mapping[str, Case], params: Params, data_end: datetime | None = None
) -> list[TierModel]:
    """The per-tier baseline models (REQ-STAT-POP.1); built once per detection result and reused."""
    end = data_end or max((c.open_utc for c in cases.values()), default=None)
    if _TIERS.get("result") is result and _TIERS.get("cases") is cases and _TIERS.get("key") == (params, end):
        return _TIERS["models"]
    areas, _km = neighborhood_geometry(con) if con is not None else ({}, {})
    models = tier_models(cases, result, params, end, areas)
    _TIERS.clear()
    _TIERS.update(result=result, cases=cases, key=(params, end), models=models)
    return models


def make_grid_metrics(con: Any) -> GridMetrics:
    """The observer the engine hands to `run_grid` (REQ-STAT-GRID.1)."""
    return GridMetrics(neighborhood_geometry(con)[0])


def zombie_baselines(con: Any, result: DetectionResult, cases: Mapping[str, Case], params: Params) -> dict[str, float]:
    """`baseline_p` per zombie (REQ-STAT-BASE.4); the engine rescores confidence with it (REQ-CONF.1-2)."""
    pooled = get_model(con, result, cases, params)
    return TierBaselines(get_tier_models(con, result, cases, params), result, pooled).zombie_baselines()


def build_stats(
    result: DetectionResult,
    cases: Mapping[str, Case],
    data_version: str,
    data_end: datetime,
    params: Params = DEFAULT,
    labels_dir: Path | None = None,
    dataset: str = "full",
    *,
    con: Any = None,
    exclusions: Mapping[str, int] | None = None,
    seed: int = SEED,
    shift_runs: int = 1000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(payloads by file name, status) for the stats stage, unvalidated."""
    status: dict[str, Any] = {"calibration_warning": None, "warnings": [], "dataset": dataset}
    model = get_model(con, result, cases, params, data_end)
    tms = get_tier_models(con, result, cases, params, data_end)
    tier_p = TierBaselines(tms, result, model)
    _areas, street_km = neighborhood_geometry(con) if con is not None else ({}, {})
    payloads: dict[str, Any] = {}

    # scorecard: raw, adjusted, with and without city-originated re-reports (REQ-STAT-SF, REQ-STAT-CITY.1, REQ-STAT-TIER.1)
    payload = scorecard_payload(
        scorecards(result, cases, data_end, params, baseline=tier_p.p), result, data_version, params, dataset
    )
    only = city_only_incidents(result, cases)
    payload["without_city_originated"] = {
        "scorecards": [c.to_json() for c in scorecards(result, cases, data_end, params, baseline=tier_p.p, skip_resurrections=only)],
        "counts": city_counts(result, cases),
    }
    payloads["scorecard.json"] = payload

    # excess, shift test, placebo, neighborhood check (REQ-STAT-BASE, -NBR, -SHIFT, -PLACEBO, -REP.2)
    intensity = intensity_by_neighborhood(cases, street_km, result.mirror_ids)
    rows = []
    for r in [*tier_excess_rows(tms, seed), *band_excess_rows(tms, seed)]:
        row = r.to_json()
        if r.kind == "neighborhood":
            if r.name not in intensity:  # never a neighborhood number without its reporting intensity (REQ-STAT-REP.2)
                continue
            row["reports_per_km"] = intensity[r.name]
        rows.append(row)
    by_tier: dict[str, Any] = {}
    shift = placebo = None
    for tm in (t for t in tms if t.tag == t.tier):  # one shift test and placebo per tier population (REQ-STAT-POP.3); the
        # headline one covers the originals whose label is not a planned-follow-up label (the other headline model has no own placebo)
        sh, pl = shift_and_placebo(tm.model, seed, shift_runs)
        by_tier[tm.tier] = {
            "model": tm.tag, **({"shift": sh.to_json()} if sh is not None else {}),
            **({"placebo": pl.to_json()} if pl is not None else {}),
        }
        if tm.tier == "headline":
            shift, placebo = sh, pl
    head_sources: dict[str, int] = {"spot": 0, "neighborhood": 0, "citywide": 0, "none": 0}
    head_burst: dict[str, int] = {}
    for tm in (t for t in tms if t.tier == "headline"):
        cohort = tm.model.excess_cohort("headline")
        for k, v in tm.model.fallback_counts(cohort).items():
            head_sources[k] += v
        for k, v in tm.model.burst_summary(cohort).items():
            head_burst[k] = head_burst.get(k, 0) + v
    excess: dict[str, Any] = {
        "data_version": data_version, "dataset": dataset, "params": params_json(params), "seed": seed, "rows": rows,
        "baseline_sources": head_sources, "burstiness": head_burst, "neighborhood_check": "ran" if model.areas_m2 else "skipped",
        "counts": counts_by_tier(result), "by_tier": by_tier, "match_modes": mode_counts(result),
    }  # fmt: skip
    if shift is not None:
        excess["shift"] = shift.to_json()
    if placebo is not None:
        excess["placebo"] = placebo.to_json()
        if placebo.calibration_warning:
            status["calibration_warning"] = (
                f"placebo excess {placebo.excess:.1f} (95% interval {placebo.lo:.1f} to {placebo.hi:.1f}) excludes 0"
            )
    if not model.areas_m2:
        status["warnings"].append("neighborhood boundaries unavailable: neighborhood check and reports per km skipped")
    payloads["excess.json"] = excess

    # survival: the engine's detector at the horizon window (REQ-STAT-KM.1)
    cs = sorted(cases.values(), key=lambda c: c.id)
    p365 = horizon_params(params)
    edges = sql_edges(con, cs, p365) if con is not None else None
    horizon = detect(cs, p365, edges) if edges is not None else detect(cs, p365)
    payloads["survival.json"] = survival_payload(horizon, dict(cases), data_end, data_version, params, dataset)

    # groups, funnel (REQ-STAT-EB, -FUNNEL, -REP, -TIER)
    groups, funnel = groups_payload(result, cases, data_end, data_version, params, dataset, street_km)
    payloads["groups.json"], payloads["funnel.json"] = groups, funnel

    payloads["trends.json"] = trend_payload(result, cases, data_end, data_version, params, dataset)  # REQ-STAT-TREND.1
    payloads["temporary_fixes.json"] = temporary_payload(result, data_end, data_version, params, dataset, exclusions)
    if con is not None:
        grid = grid_payload(con, data_version, params, dataset)
        if grid is not None:
            payloads["sensitivity_grid.json"] = grid

    # validation and the tour (REQ-STAT-VAL, REQ-STAT-TOUR)
    val = score(read_sample_ids(labels_dir / SAMPLE_FILE), read_labels(labels_dir / LABELS_FILE)) if labels_dir else None
    if val is not None:
        payloads["validation.json"] = {**val.to_json(data_version), "dataset": dataset, "params": params_json(params), "seed": None}
    override = read_override(labels_dir / OVERRIDE_FILE) if labels_dir else None
    tour = build_tour(result.zombies, override, val.confirmed if val is not None else None)
    if tour is None:
        status["warnings"].append("judge_tour.json not written: fewer than 3 headline zombies")
    else:
        payloads["judge_tour.json"] = tour.to_json(data_version, params, dataset)
        if override is not None and tour.source != "override":
            status["warnings"].append(f"{OVERRIDE_FILE} ignored: it must list 3 distinct headline zombie IDs")
    status["baseline_sources"] = excess["baseline_sources"]
    return payloads, status


def run_stats(
    con: Any,
    result: DetectionResult,
    by_id: Mapping[str, Case],
    out: Path,
    *,
    params: Params = DEFAULT,
    data_version: str = "unknown",
    data_end: datetime | None = None,
    labels_dir: Path | None = None,
    dataset: str = "full",
    exclusions: Mapping[str, int] | None = None,
    seed: int = SEED,
) -> dict[str, Any]:
    """Validate, then write the stats files under `<out>/stats/` (REQ-STAT-EXP.1). Returns the stats status."""
    end = data_end or max((c.open_utc for c in by_id.values()), default=None)
    folder = Path(out) / "stats"
    if end is None:
        payloads: dict[str, Any] = {}
        status: dict[str, Any] = {"calibration_warning": None, "warnings": ["no cases"], "dataset": dataset}
    else:
        payloads, status = build_stats(
            result, by_id, data_version, end, params, labels_dir, dataset, con=con, exclusions=exclusions, seed=seed
        )
        for name, payload in payloads.items():
            validate(name.removesuffix(".json"), payload)
    for name in sorted(payloads):
        write_text_atomic(folder / name, canonical_json(payloads[name]))
    for name in STAT_FILES:  # a file from an earlier run must not outlive a run that did not produce it
        if name not in payloads:
            (folder / name).unlink(missing_ok=True)
    write_text_atomic(folder / "stats_status.json", canonical_json(status))
    return status
