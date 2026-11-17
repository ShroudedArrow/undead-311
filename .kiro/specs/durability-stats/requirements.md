# Requirements: durability-stats

## Introduction
Durability statistics answer one question: how many possible zombies are more than coincidence, and how long fixes last. They implement `.kiro/steering/methods.md` on the engine's outputs (incidents, zombies, cases). Every statistic is computed for the **headline** tier. The same statistics with `source_unknown` and `sensitivity` zombies added are exported beside it as the sensitivity toggle; the headline is never silently mixed with other tiers. Outputs are static JSON files with schemas, written to `web/public/data/stats/`.

IDs use the prefix `REQ-STAT-`. Layers follow docs/PROJECT.md: **demo-critical** (by Nov 17), **credibility** (by Nov 22), **delight**. Acceptance criteria are in EARS form.

## Glossary
- **Eligible original:** an incident that can be an original under ZD step 3 (not transferred) and is fully observed: `close_time + WINDOW_DAYS <=` data end.
- **Spot:** the matching location unit: the `segment_id` when snapped, else a 60 m grid cell (2 × RADIUS_M).
- **Season:** the meteorological season (Dec–Feb, Mar–May, Jun–Aug, Sep–Nov).
- **Group:** a department, family or neighborhood, as named in each requirement.

---

### REQ-STAT-SF: Two-number scorecard
**Layer:** demo-critical (raw rates with intervals); credibility (adjusted rate)
**User story:** As a resident or councilor, I want "closed on time" next to "stayed fixed" for each category, so the speed metric isn't the only number.
1. THE stats SHALL compute, per family and citywide, the on-time rate: the share of closed in-scope cases in eligible originals whose `on_time` is true. Cases with null `on_time` are left out and counted.
2. THE stats SHALL compute the raw stayed-fixed rate: the share of those cases that are on time AND whose incident is not a headline possible zombie within WINDOW_DAYS. Planned follow-ups and separate deaths count as not resurrected.
3. WHEN the baseline is available, THE stats SHALL compute the adjusted stayed-fixed rate by adding back the expected coincidental resurrections (REQ-STAT-BASE) among on-time cases, and SHALL clamp it so it never exceeds the on-time rate.
4. THE stats SHALL publish a Wilson 95% interval for every rate, and the denominators.

### REQ-STAT-INT: Intervals everywhere
**Layer:** demo-critical
**User story:** As a reader, I want uncertainty next to every number, so small groups don't look certain.
1. THE stats SHALL attach a 95% interval to every exported rate (Wilson for proportions; bootstrap with a fixed seed for excess counts).
2. IF a denominator is 0, THEN THE stats SHALL export the rate as null with the reason `no_cases`, never 0.

### REQ-STAT-BASE: Same-spot baseline and excess
**Layer:** credibility
**User story:** As a skeptic, I want each spot compared with itself, so busy places don't produce zombies by chance.
1. FOR each eligible original, THE stats SHALL estimate `p_spot` with the season-integrated estimator in methods.md ("Primary baseline"): the chance that a window of WINDOW_DAYS holds at least one other same-family report at the same spot, integrated over the seasons the window spans (`p = 1 - prod_s (1 - d_s/T_s)^K_s`), from the spot's reports and live days outside the WINDOW_DAYS that follow any same-family closure there. THE placebo (REQ-STAT-PLACEBO) SHALL call the same estimator code as the excess.
2. THE stats SHALL compute expected resurrections as Σ `p_spot` and excess resurrections as observed headline zombies − expected, by department, family and neighborhood, with bootstrap intervals.
3. WHEN a spot has fewer than 4 comparable windows, THE stats SHALL use the neighborhood estimate (REQ-STAT-NBR) for that original and count how often this happens.
4. THE stats SHALL write `baseline_p` per zombie for the engine's confidence score.

### REQ-STAT-NBR: Neighborhood Poisson check
**Layer:** credibility
**User story:** As a reader, I want a second, independent baseline, so the result doesn't rest on one method.
1. FOR each eligible original, THE stats SHALL estimate λ = same-family reports per m² per day in its neighborhood and season, excluding reports within RADIUS_M and ±WINDOW_DAYS of the case. It SHALL compute `P = 1 − exp(−λ·A·D)` and expected = `λ·A·D`, with A = π·RADIUS_M² and D = WINDOW_DAYS.
2. THE stats SHALL take neighborhood areas from the Analyze Boston neighborhood boundaries file, recorded in data/SNAPSHOT.md.

### REQ-STAT-SHIFT: Shift test (robustness)
**Layer:** credibility
**User story:** As a skeptic, I want to see how many zombies appear by chance alone, so the excess can be judged.
1. THE stats SHALL circularly shift closure times by random offsets per spot (locations fixed), rerun candidate counting, and repeat 1,000 times with a fixed seed (default 311). It SHALL report the distribution (mean, 2.5% and 97.5% quantiles) beside the observed count.
2. WHEN run twice with the same seed and input, THE shift test SHALL return identical results.

### REQ-STAT-PLACEBO: Placebo calibration
**Layer:** credibility
**User story:** As the owner, I want proof that the baseline isn't biased, so the excess means something.
1. THE stats SHALL apply the baseline (REQ-STAT-BASE) to the time-shifted closures and report the placebo excess with its interval.
2. IF the placebo excess interval excludes 0, THEN THE stats SHALL write a `calibration_warning` into `status.json` and the methods data.

### REQ-STAT-REP: Reporting intensity
**Layer:** credibility
**User story:** As a reader, I want resurrection rates shown with how much each area reports, so low-reporting areas don't look better than they are.
1. THE stats SHALL compute reports per km of street (from SAM segment lengths) per neighborhood and family. It SHALL export it beside every neighborhood rate, with the note that measured counts are a floor.
2. THE stats SHALL never export a neighborhood ranking without the intensity value.

### REQ-STAT-CITY: With and without city-originated re-reports
**Layer:** credibility
**User story:** As a reader, I want to see results with and without city staff re-reports, so staff activity isn't mistaken for failures.
1. THE stats SHALL compute the headline counts and rates twice: with all re-reports, and with city-originated re-reports removed (legacy only; new-system origin is unknown and is stated as such).

### REQ-STAT-KM: Survival curves
**Layer:** credibility
**User story:** As a reader, I want to see how long fixes last, so durability is shown, not only counted.
1. THE stats SHALL compute Kaplan–Meier curves of time from incident close to its first resurrection. The event is the first re-report that would make a possible zombie under every rule of ZD steps 2–9, with WINDOW_DAYS replaced by SURVIVAL_HORIZON_DAYS = 365, by department and family. Curves are right-censored at the data end or the horizon. The horizon is a proposed new parameter: it is needed because methods.md asks for the 90-day share, which a 60-day window cannot give. It is to be written into methods.md by the owner.
2. THE stats SHALL export the share still holding at 7, 30 and 90 days with 95% intervals (Greenwood), and the median "fix half-life" where the curve crosses 0.5, else null.
3. THE stats SHALL compute curves for the headline tier and, separately, for all tiers.

### REQ-STAT-EB: Small-sample correction
**Layer:** credibility
**User story:** As a department manager, I want small groups pulled toward the citywide rate, so a tiny group isn't extreme by chance.
1. THE stats SHALL shrink each group's resurrection rate with a beta-binomial model whose prior mean is the citywide rate. The prior concentration SHALL be fitted by maximum marginal likelihood (method of moments as fallback).
2. THE stats SHALL export raw rate, shrunk rate, interval and n for every group.

### REQ-STAT-FUNNEL: Funnel plot data
**Layer:** credibility
**User story:** As a reader, I want fair comparisons, so only real outliers are called unusual.
1. THE stats SHALL export each group's rate against its n, with exact binomial 95% and 99.8% control limits around the citywide rate for n from 1 to the maximum group n.
2. THE stats SHALL label a group `unusual` only when it lies outside the 99.8% limits.

### REQ-STAT-GRID: Sensitivity grid
**Layer:** credibility
**User story:** As a judge, I want to change radius, window and matching mode and see the result, so the definition isn't cherry-picked.
1. THE stats SHALL turn the engine's sensitivity runs (REQ-SENS-RUN) into `sensitivity_grid.json`: headline count, excess and stayed-fixed rate per grid point, plus all-tier counts. It SHALL include the run without Street Light Other.

### REQ-STAT-POP: Baseline population per tier
**Layer:** credibility
**User story:** As a reader of the excess, I want each tier compared with the reports it could have come from, never with a pooled count.
1. THE baseline of a tier SHALL count only reports from that tier's population (`stats/tiers.py`): headline, resident legacy and new-system reports (resident legacy only for originals with a planned-follow-up label); source_unknown, new-system reports; city_rereport, legacy city-originated reports; sensitivity, every report. Closures of every same-family case still open a dead stretch.
2. Excess SHALL be reported per tier (`tier_set` is the tier) and never pooled across tiers; originals labeled invalid or duplicate are in no cohort.
3. Each tier SHALL have its own shift test and placebo (`by_tier` in `excess.json`).

4. The source_unknown cohort SHALL hold only originals whose window ends after the first new-system case (owner decision 2026-11-16): before that no new-system report can exist.
5. WHEN the headline placebo interval does not cover 0, the excess SHALL be shown nowhere on the site and the methods page SHALL show the placebo result instead (methods.md).

### REQ-STAT-SF.4: Adjusted rate withheld
**Layer:** credibility
1. No export SHALL carry the adjusted stayed-fixed rate (`stayed_fixed_adj` is null) and the site SHALL show only the raw stayed-fixed rate beside the on-time rate (owner decision 2026-11-17); the methods page SHALL say that the adjustment depends on the same uncalibrated baseline as the excess, and that the confidence score's chance term comes from that baseline and the score is used only for ranking.

### REQ-STAT-AREA: Match-area baseline
**Layer:** credibility
1. Each original's `p` SHALL be estimated from the history of its own match area (`stats/areas.py`): the same-family cases that match any of its members under `detect.match.match` (same segment within MAX_SEGMENT_DIST, the intersection rule, or RADIUS_M when unsnapped). Reports outside the area SHALL never change the original's `p`.
2. Originals of one segment or cell SHALL be resampled together, and their closures moved together in the shift test and placebo.

### REQ-STAT-BAND: Excess by match distance
**Layer:** credibility
1. Observed, expected and excess SHALL also be reported per tier and match-distance band (0-5, 5-15, 15-30, 30-75 m): observed by the zombie's `distance_m`, expected by splitting each original's `p` by the distance distribution of the spot's other live reports. The rows are a diagnostic; `p` still counts the whole spot (docs/METHODS.md).

### REQ-STAT-TIER: Sensitivity toggle data
**Layer:** credibility
**User story:** As a reader, I want to switch the sensitivity tier on and off, so I can see what the headline leaves out.
1. FOR every exported statistic, THE stats SHALL export the headline value and the "all tiers" value side by side, plus the counts of `source_unknown` and `sensitivity` zombies.
2. THE stats SHALL never fold `source_unknown` or `sensitivity` zombies into headline values.

### REQ-STAT-VAL: Validation precision
**Layer:** credibility
**User story:** As the owner, I want a field-checked precision with an honest interval, so the headline is credible.
1. `make validation-sample` SHALL draw 50 recent possible zombies (headline tier, re-reported within 60 days of the snapshot end) from the neighborhoods listed in `data/labels/validation_config.json`, with a fixed seed. It SHALL write `data/labels/validation_sample.csv` without the confidence score (raters are blind to it). The file is committed before any visit.
2. `make validate` SHALL read the two raters' labels (`data/labels/validation_labels.csv`; labels: still broken / fixed since / different issue / can't tell, per methods.md). It SHALL report precision = still broken ÷ (rated, excluding can't tell) with a Wilson 95% interval, the can't-tell share, and Cohen's kappa, into `docs/VALIDATION.md` and `validation.json`.
3. THE stats SHALL list the "confirmed" set (both raters said still broken) for judge mode.
4. IF the label file is missing, THEN `make validate` SHALL report "awaiting field labels" and exit 0.

### REQ-STAT-TEMP: How often temporary fixes come back
**Layer:** credibility
**User story:** As a reader, I want to know how often "made safe" repairs come back, so temporary fixes are visible (ZD step 6).
1. THE stats SHALL compute, by family and department, the share of eligible originals labeled `made_safe_temporary` that became a possible zombie tagged `after_temporary_fix` (legacy) or `source_unknown` (new system, shown separately), with Wilson intervals.
2. THE stats SHALL export the counts of separate deaths (`invalid`, `duplicate`) and of exclusions beside it for the methods page.

### REQ-STAT-TOUR: Judge-mode tour file
**Layer:** demo-critical (provisional); credibility (confirmed)
**User story:** As a judge, I want the tour to show only field-confirmed zombies, so the demo is the strongest evidence; as the owner, I want a working tour before field validation, so I can storyboard the video.
1. WHILE the confirmed validation set doesn't exist, THE stats SHALL write `judge_tour.json` with `provisional: true`. It SHALL list the three zombies named in `data/labels/judge_tour_override.json` when that file exists, else the three headline zombies with the most re-reports (ties by zombie ID). Never by confidence score.
2. WHEN the confirmed set exists (REQ-STAT-VAL.3), THE stats SHALL write `provisional: false` and choose the three tour zombies only from it: the owner's override if every listed ID is confirmed, else the confirmed zombies with the most re-reports.

### REQ-STAT-EXP: Stats exports
**Layer:** demo-critical (scorecard file); credibility (the rest)
**User story:** As the web app, I want validated stats files, so charts can't show numbers that don't match the pipeline.
1. THE stats SHALL write `scorecard.json` (demo-critical), plus `excess.json`, `survival.json`, `funnel.json`, `groups.json`, `sensitivity_grid.json`, `temporary_fixes.json`, `validation.json` and `judge_tour.json`, to `web/public/data/stats/`. Each validates against its schema in `/schemas/` and carries `data_version`.
2. THE stats SHALL be deterministic for a fixed seed and input.

### REQ-STAT-CREATIO: Before and after the system change
**Layer:** delight
**User story:** As a journalist, I want resurrection rates before and after each type moved to the new system, so the switch's effect is visible.
1. THE stats SHALL compare rates before and after each family's move, using not-yet-moved families as the comparison group. Every output SHALL carry a warning that format changes can create artifacts.

### REQ-STAT-TREND: Rolling trends
**Layer:** delight
**User story:** As a journalist, I want trends that don't jump month to month, so a single odd month doesn't become a headline.
1. WHEN trends are exported, THE stats SHALL use rolling 6-month windows, never single months.
