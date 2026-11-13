---
inclusion: fileMatch
fileMatchPattern: ["**/pipeline/undead311/stats/**", "**/pipeline/undead311/detect/**", "**/docs/METHODS.md"]
---
# Statistical methods

## Primary baseline: the same spot as its own control
Reports cluster in busy places, so a citywide Poisson rate understates coincidence. Primary comparison: for each location (segment), compare the re-report rate in the window right after a closure with the same location's rate in comparable windows that did NOT follow a closure (same season). Excess = after-closure rate minus same-spot typical rate. The neighborhood Poisson model below is the secondary check.

## Secondary baseline (neighborhood rate)
For each closed case, local background rate λ = same-family reports per m² per day in its neighborhood and season, excluding a buffer window around the case. With match area A = π·RADIUS_M² and window D:
- P(≥1 by chance) = 1 − exp(−λ·A·D); expected = λ·A·D
- **Excess resurrections** = observed − Σ expected, by department, family, neighborhood.
- Robustness: circularly shift closure times by random offsets (fixed seed, 1,000 runs); report the chance distribution.

## Survival (how long fixes last)
Time from closure to first resurrection; right-censor at data end. Kaplan-Meier by department and family; report share holding at 7/30/90 days and median "fix half-life" where defined.

## Fair comparisons
- Empirical-Bayes (beta-binomial) shrinkage of group rates toward the citywide rate.
- Funnel plots: rate vs. case count with 95% and 99.8% control limits.
- Every displayed rate has an interval.

## Stayed-fixed on-time rate
Raw: share closed on time AND not resurrected within WINDOW_DAYS. Adjusted: subtract expected coincidences. Always show beside the plain on-time rate. Invariant: stayed-fixed ≤ on-time.

## Should-have analyses
- Weather: DROPPED. The same-spot baseline compares like seasons, which already absorbs freeze-thaw surges; a separate weather join isn't worth the complexity.
- Street segments: match on same segment when available.
- Creatio switch: compare rates before/after each type migrated, using not-yet-migrated types as comparison; warn about format artifacts.

## Reporting bias (counts are a floor)
A zombie appears only if someone reports again. Show resurrection rates next to local reporting intensity (reports per 1,000 residents or per km of street); call measured rates a floor; never rank neighborhoods without this context.

## Calibration and robustness
- Placebo check: run the detector on random time-shifted closures; the excess over baseline should be near zero.
- Show results with and without city-originated re-reports.
- Trends use rolling multi-month windows (avoid regression-to-the-mean headlines from single months).
- Label groups "unusual" only outside the 99.8% funnel limits.

## Validation
Field validation uses RECENT possible zombies (re-reported within the last ~60 days of the snapshot), so the site visit still means something; older zombies are judged from case records only. Sample 40–50, solo shortcut: within 3–4 easily reached neighborhoods, stated as a limitation (at 50 the 95% interval is about ±12–13 points; at 40 about ±14), drawn with a fixed seed and committed before any visit → two raters label each independently, blind to the confidence score (solo project: you visit and photograph each site; a volunteer friend rates the same cases from your photos and the case records) (still broken / fixed since / different issue / can't tell) → report precision with a Wilson 95% interval and inter-rater agreement (Cohen's kappa) in `docs/VALIDATION.md`. Record visit dates against case dates.
