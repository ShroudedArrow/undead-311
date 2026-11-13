# Design: durability-stats

## Overview
A subpackage `pipeline/undead311/stats/` that reads the engine's DuckDB tables (`cases_clean`, `incidents`, `zombies`, `excluded_pairs`) and writes `web/public/data/stats/*.json`. Rates and counts are SQL in DuckDB. Kaplan–Meier uses `lifelines`, beta-binomial fitting uses `scipy`, and resampling uses `numpy.random.Generator(PCG64(seed))`. Every function takes an explicit seed and returns plain dataclasses, so property tests can call it on generated data.

## Architecture
```
DuckDB (engine tables) ─► stats.cohort (eligible originals, censoring) ─► stats.rates (on-time, stayed-fixed, Wilson)
                                                     │                                    ▲
                                                     ├─► stats.baseline (same-spot p_spot, neighborhood λ) ─► baseline_p back to engine
                                                     ├─► stats.shift (circular shifts, placebo)
                                                     ├─► stats.survival (KM, Greenwood, half-life)
                                                     ├─► stats.groups (EB shrinkage, funnel limits, reporting intensity)
                                                     ├─► stats.grid (sensitivity grid from engine runs)
                                                     └─► stats.validation (sample draw, precision, kappa)
                                                                     ▼
                                              stats.export (schemas, data_version) ─► web/public/data/stats/
```
Run order inside `make pipeline`: engine detect, then `stats.baseline` (writes `baseline_p`), then the engine re-scores confidence (`confidence_partial` turns false), then the rest of the stats, then export.

### Components
| Module | Interface | Requirements |
|---|---|---|
| `stats/intervals.py` | `wilson(k, n, z=1.96) -> (lo, hi)`, `bootstrap(values, fn, seed, B=1000)` | REQ-STAT-INT |
| `stats/cohort.py` | `eligible_originals(con, params, data_end)`; spot keys; seasons | glossary, REQ-STAT-SF |
| `stats/rates.py` | `scorecard(con, tier_set) -> Scorecard` with on-time, raw stayed-fixed, adjusted (clamped) | REQ-STAT-SF, REQ-STAT-TIER |
| `stats/baseline.py` | `same_spot(con, params) -> {incident_id: p_spot}`, `neighborhood(con, areas) -> {incident_id: (P, expected)}`, `excess(...)` | REQ-STAT-BASE, -NBR |
| `stats/shift.py` | `shift_test(con, params, seed, runs=1000)`, `placebo(...)` | REQ-STAT-SHIFT, -PLACEBO |
| `stats/survival.py` | `km(durations, events) -> Curve` (lifelines), `holding_at(curve, [7, 30, 90])`, `half_life(curve)` | REQ-STAT-KM |
| `stats/groups.py` | `shrink(groups, citywide) -> list[Group]`, `funnel_limits(p0, n_max)`, `intensity(con, segments)` | REQ-STAT-EB, -FUNNEL, -REP |
| `stats/grid.py` | `grid_table(engine_runs, baseline)` | REQ-STAT-GRID |
| `stats/validation.py` | `draw_sample(con, config, seed)`, `precision(labels)`, `kappa(a, b)` | REQ-STAT-VAL |
| `stats/tour.py` | `build_tour(zombies, validation, override) -> JudgeTour` | REQ-STAT-TOUR |
| `stats/temporary.py` | `temporary_fix_rates(con)`, separate-death and exclusion counts | REQ-STAT-TEMP |
| `stats/export.py` | Writers with schema validation | REQ-STAT-EXP |

### Key formulas
- **Wilson interval** for k of n at z = 1.96. Shown as null with `no_cases` when n = 0.
- **Adjusted stayed-fixed:** `adj = min(on_time, raw + E_on_time / n)`, where `E_on_time` = Σ `p_spot` over on-time eligible originals that are headline zombies, capped at the number of those zombies. The min() is the clamp in methods.md.
- **Shrinkage:** prior Beta(μ·κ, (1−μ)·κ) with μ = the citywide rate (fixed) and κ fitted. The posterior mean is `(k + μκ)/(n + κ)` = w·raw + (1−w)·μ with w = n/(n+κ) ∈ [0, 1], so the shrunk rate always lies between raw and citywide (property 8).
- **Funnel limits:** exact binomial quantiles of Bin(n, p0) / n at 0.025/0.975 and 0.001/0.999.
- **KM:** the event is the first re-report that would be a possible zombie under ZD steps 2–9 with the window set to SURVIVAL_HORIZON_DAYS (365). The engine's `detect()` is called with that one parameter changed, so the rules are not duplicated. This is longer than WINDOW_DAYS so that the 90-day share exists, and is recorded as a departure in docs/DECISIONS.md.
- **Kappa:** Cohen's kappa over the four labels, plus a 2×2 version (still broken vs. not) for the headline.

## Data models
`Scorecard{family, n_closed, n_on_time_known, on_time{rate, lo, hi}, stayed_fixed_raw{rate, lo, hi}, stayed_fixed_adj{rate, lo, hi} | null, tier_set: "headline" | "all"}`. `Group{kind, name, n, k, raw, shrunk, lo, hi, unusual, reports_per_km}`. `Curve{times[], survival[], lo[], hi[], at_7, at_30, at_90, half_life}`. `JudgeTour{provisional, zombie_ids[3], source: "override" | "most_reports"}`. Every file has `data_version`, `params` and `seed`. Stats writes its status (`calibration_warning`, warnings) to `stats_status.json`, which the engine's export folds into `status.json` last.

## Correctness properties
| # | Property | testing.md | Requirements |
|---|---|---|---|
| P1 | Every exported rate and interval bound is within [0, 1] (or null with a reason); `lo <= rate <= hi` | 3 | REQ-STAT-INT, REQ-STAT-SF |
| P2 | Survival curves start at 1 and never increase; interval bounds are within [0, 1] | 6 | REQ-STAT-KM |
| P3 | Excess counts, shift-test and placebo results are identical for a fixed seed and input | 7 | REQ-STAT-SHIFT, REQ-STAT-BASE |
| P4 | Each shrunk group rate lies between that group's raw rate and the citywide rate (inclusive) | 8 | REQ-STAT-EB |
| P5 | Raw stayed-fixed rate <= on-time rate for every group | 10 | REQ-STAT-SF.2 |
| P6 | Adjusted stayed-fixed rate <= on-time rate for every group (clamp), and >= raw stayed-fixed | 17 | REQ-STAT-SF.3 |
| P7 | Headline values never change when `source_unknown` or `sensitivity` zombies are added to the input; all-tier counts = headline + source_unknown + sensitivity | owner (new) | REQ-STAT-TIER |
| P8 | Funnel limits are nested (99.8% contains 95%) and narrow as n grows | — | REQ-STAT-FUNNEL |
| P9 | Wilson precision interval contains the point estimate, and kappa is within [−1, 1] | — | REQ-STAT-VAL |
| P10 | A non-provisional tour contains only confirmed IDs; tour selection is invariant to the confidence scores (permuting confidence changes nothing) | — | REQ-STAT-TOUR |

Tests are Hypothesis tests named `test_prop_stat_<n>_<slug>`, citing requirement IDs. Generators produce small cohorts (group sizes 0 to 200, rates 0 to 1, censoring patterns, and tier mixes).

## Error handling
- Missing neighborhood boundaries: the neighborhood check is skipped with a status flag. The same-spot baseline still runs.
- Too few comparable windows: fall back to the neighborhood estimate (REQ-STAT-BASE.3), with the count reported.
- Missing validation labels: "awaiting field labels" (exit 0).
- A placebo failure is a warning, not a crash. It is shown on the methods page.

## Testing strategy
Unit tests per formula against hand-computed examples (Wilson, KM on a 5-case toy, funnel quantiles, kappa), property tests P1–P9, and one slow end-to-end check on `data/sample`. New dependencies: `lifelines`, `scipy`, `numpy` (all named in tech.md).
