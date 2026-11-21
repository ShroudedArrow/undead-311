vvv---
inclusion: fileMatch
fileMatchPattern: ["**/pipeline/undead311/stats/**", "**/pipeline/undead311/detect/**", "**/docs/METHODS.md"]
---
# Statistical methods

## Primary baseline: the same spot as its own control
 Reports cluster in busy places, so a citywide rate understates coincidence. Primary baseline: for each original, the chance that a same-family report from the same tier's population lands in its window anyway, estimated from the history of the original's own match area (the reports that would count as a match: same segment within MAX_SEGMENT_DIST, the intersection rule, or within RADIUS_M when unsnapped), outside after-closure windows. "Spot" below means this match area.
- Sparse spots (on average fewer than one report per two windows, i.e. per 2 × WINDOW_DAYS days): season by season, p = 1 − Π_s (1 − d_s/T_s)^K_s, where K_s is the spot's report count and T_s its observed days in season s (outside after-closure windows), and d_s is how many of the window's days fall in season s.
- Dense spots (at least one report per two windows): p = the share of sliding WINDOW_DAYS-day windows, starting on days in the same season and outside after-closure windows, that contain at least one report.
Excess = observed zombies − Σ p. The placebo check uses the same estimator.
Acceptance and limits: in seeded null towns whose reporting matches the model (sparse random, seasonal, near-regular 30-day), the excess interval must never lie above 0. Reporting the model does not capture (bursty spots, spots reported only during a limited period) can push the excess above 0; the methods page states the size and direction of that bias, measured on null towns.    Burstiness flag: assessed only for spots with at least 8 reports; a spot is flagged if the index of dispersion of its monthly report counts is above 2, or if its reports fall in fewer than half as many distinct months as a random spread would give (expected distinct months = M·(1 − (1 − 1/M)^K) for K reports over M observed months). Spots with fewer than 8 reports are never flagged. The scorecard reports the excess with and without flagged spots, and the excess is never the headline number. The survival analysis uses a 365-day horizon. The neighborhood Poisson model below is the secondary check. If the headline placebo interval does not cover 0 on the judged data, the excess is not shown anywhere on the site; the methods page shows the placebo result instead.

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
Validation: the 50-site sample (seed 311, drawn at the judging snapshot) is checked against the City's own records instead of field visits. Each re-report's closure is classified as repaired again, duplicate, invalid or nothing found, referred, still open, or other, by rules fixed before any closure was read. The share repaired again is reported with a 95% interval, alongside the higher figure if ambiguous repairs counted. This measures what crews recorded, not field conditions; there is one reader and no second rater. Judge-mode zombies are record-confirmed (repaired again) when no field labels exist.
