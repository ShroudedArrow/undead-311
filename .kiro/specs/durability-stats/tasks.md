# Tasks: durability-stats

Layer tags drive the build order: all `[demo-critical]` tasks in every spec first, then `[credibility]`, then `[delight]`. Definition of done per task: `make test` passes, `ruff check` clean, tests cite requirement IDs, one line in docs/KIRO_LOG.md.

## Demo-critical

- [ ] 1. [demo-critical] Intervals
  - `stats/intervals.py`: Wilson (null with `no_cases` at n = 0) and seeded bootstrap.
  - [ ] 1.1 Property P1 (part 1): every interval is within [0, 1] and contains its estimate. _REQ-STAT-INT.1–2_
  - _Requirements: REQ-STAT-INT.1–2_
- [ ] 2. [demo-critical] Cohort
  - `stats/cohort.py`: eligible originals (not transferred, fully observed), spot keys (segment or 60 m cell), seasons.
  - _Requirements: REQ-STAT-SF.1 (denominator), glossary_
- [ ] 3. [demo-critical] Raw scorecard
  - `stats/rates.py`: on-time and raw stayed-fixed per family and citywide, with intervals and denominators; `scorecard.json` plus schema in `/schemas/`.
  - [ ] 3.1 Property P5: raw stayed-fixed ≤ on-time for every group. _REQ-STAT-SF.2; testing.md #10_
  - [ ] 3.2 Property P1 (part 2): every exported rate is within [0, 1] or null with a reason. _testing.md #3_
  - _Requirements: REQ-STAT-SF.1, .2, .4, REQ-STAT-EXP.1 (scorecard)_
- [ ] 4. [demo-critical] Provisional judge tour
  - `stats/tour.py`: `judge_tour.json` (`provisional: true`, owner override or the three headline zombies with the most re-reports) plus schema.
  - [ ] 4.1 Property P10 (part 1): tour selection doesn't change when confidence scores are permuted. _REQ-STAT-TOUR.1_
  - _Requirements: REQ-STAT-TOUR.1_

## Credibility

- [ ] 5. [credibility] Same-spot baseline and excess
  - `stats/baseline.py`: comparable windows, `p_spot`, neighborhood fallback below 4 windows (counted), expected, excess with bootstrap intervals by department, family and neighborhood; write `baseline_p` per zombie.
  - _Requirements: REQ-STAT-BASE.1–4_
- [ ] 6. [credibility] Neighborhood Poisson check
  - λ per neighborhood, season and family with the exclusion buffer; P and expected; boundary file from task 21 of zombie-engine.
  - _Requirements: REQ-STAT-NBR.1–2_
- [ ] 7. [credibility] Shift test and placebo
  - `stats/shift.py`: 1,000 seeded circular shifts per spot; the distribution; placebo excess; `calibration_warning` into `stats_status.json`.
  - [ ] 7.1 Property P3: identical results for a fixed seed and input (excess, shift, placebo). _testing.md #7_
  - _Requirements: REQ-STAT-SHIFT.1–2, REQ-STAT-PLACEBO.1–2_
- [ ] 8. [credibility] Adjusted stayed-fixed rate
  - Add back expected coincidences among on-time originals; clamp to on-time.
  - [ ] 8.1 Property P6: raw ≤ adjusted ≤ on-time. _REQ-STAT-SF.3; testing.md #17_
  - _Requirements: REQ-STAT-SF.3_
- [ ] 9. [credibility] Tier toggle values
  - Headline and all-tier values side by side for every statistic, plus `source_unknown` and `sensitivity` counts.
  - [ ] 9.1 Property P7: headline values don't change when non-headline zombies are added; all-tier = sum of tiers. _REQ-STAT-TIER.1–2_
  - _Requirements: REQ-STAT-TIER.1–2_
- [ ] 10. [credibility] Survival curves
  - `stats/survival.py`: events from `detect()` with the window set to SURVIVAL_HORIZON_DAYS; lifelines KM by department and family; Greenwood intervals; 7/30/90 shares; half-life; headline and all tiers.
  - [ ] 10.1 Property P2: curves start at 1 and never increase; bounds within [0, 1]. _testing.md #6_
  - _Requirements: REQ-STAT-KM.1–3_
- [ ] 11. [credibility] Empirical-Bayes shrinkage
  - Beta-binomial with the prior mean fixed at the citywide rate; κ by maximum marginal likelihood, method-of-moments fallback.
  - [ ] 11.1 Property P4: each shrunk rate lies between raw and citywide. _testing.md #8_
  - _Requirements: REQ-STAT-EB.1–2_
- [ ] 12. [credibility] Funnel plot data
  - Exact binomial 95% and 99.8% limits; `unusual` only outside 99.8%.
  - [ ] 12.1 Property P8: limits are nested and narrow as n grows. _REQ-STAT-FUNNEL.1_
  - _Requirements: REQ-STAT-FUNNEL.1–2_
- [ ] 13. [credibility] Reporting intensity
  - Reports per km of street per neighborhood and family; attached to every neighborhood rate.
  - _Requirements: REQ-STAT-REP.1–2_
- [ ] 14. [credibility] With and without city-originated re-reports
  - _Requirements: REQ-STAT-CITY.1_
- [ ] 15. [credibility] Sensitivity grid file
  - `sensitivity_grid.json` plus schema from `grid_runs`, including the run without Street Light Other.
  - _Requirements: REQ-STAT-GRID.1_
- [ ] 16. [credibility] Temporary fixes, separate deaths, exclusions
  - `temporary_fixes.json` plus schema.
  - _Requirements: REQ-STAT-TEMP.1–2_
- [ ] 17. [credibility] Validation sample, precision and confirmed tour
  - `make validation-sample` (fixed seed, blind to confidence; owner config of neighborhoods), `make validate` (precision with Wilson interval, can't-tell share, Cohen's kappa; `docs/VALIDATION.md`, `validation.json`), the confirmed set, and `judge_tour.json` with `provisional: false` when confirmed.
  - [ ] 17.1 Property P9: the precision interval contains the estimate; kappa is in [−1, 1]. _REQ-STAT-VAL.2_
  - [ ] 17.2 Property P10 (part 2): a non-provisional tour contains only confirmed IDs. _REQ-STAT-TOUR.2_
  - _Requirements: REQ-STAT-VAL.1–4, REQ-STAT-TOUR.2_
- [ ] 18. [credibility] All stats exports
  - Schemas, `data_version`, determinism test for a fixed seed.
  - _Requirements: REQ-STAT-EXP.1–2_

## Delight

- [ ] 19. [delight] Before and after the system change
  - _Requirements: REQ-STAT-CREATIO.1_
- [ ] 20. [delight] Rolling 6-month trends
  - _Requirements: REQ-STAT-TREND.1_
