# Methods

This page is written by the engine for the parts it implements. The statistical sections (baseline, survival, fair comparisons) are owned by durability-stats and follow `.kiro/steering/methods.md`. Definitions come only from `.kiro/steering/zombie-definition.md`.

## Confidence score

**Status: pending owner approval.** The weights below are a proposal. The owner must approve them before the first full-data run (REQ-CONF.1). The score is computed in `pipeline/undead311/detect/confidence.py`.

```
confidence = clamp01(0.20*match + 0.15*gap + 0.10*specificity + 0.15*label + 0.30*baseline + 0.10*skeptic)
```

Each term is in [0, 1]:

| Term | Weight | Definition |
|---|---|---|
| match | 0.20 | segment: `1 - d / (2 * MAX_SEGMENT_DIST)`. intersection: `0.9 * (1 - d / (2 * INTERSECTION_M))`, where `d` is the sum of the two distances to the intersection. radius: `0.8 * (1 - d / RADIUS_M)`. Closer is higher; segment beats intersection beats radius. |
| gap | 0.15 | `1 - gap_days / WINDOW_DAYS` (a shorter gap is higher). |
| specificity | 0.10 | 1 for a specific type; 0.7 for a catch-all type that inherited its family from a legacy case. |
| label | 0.15 | Coroner label of the original: resolved 1.0, made_safe_temporary 0.9, noted 0.8, referred 0.7, planned_followup 0.6, other 0.6, bulk_backlog 0.5. If the incident has `bulk_closure`, the term is `min(label, 0.5)`. `invalid` and `duplicate` never reach scoring (they are separate deaths). |
| baseline | 0.30 | `1 - baseline_p`, the local chance of coincidence (lower chance of coincidence gives higher confidence). **Neutral 0.5** until durability-stats provides `baseline_p`. |
| skeptic | 0.10 | The surviving Skeptic objections: survives 1.0, weakened 0.5, explained_away 0.0. **Neutral 0.5** while the verdict is `not_reviewed` (a `weakened` verdict also scores 0.5 but is not neutral). |

`confidence_partial` is `true` exactly when a neutral term was used (no `baseline_p`, or Skeptic `not_reviewed`). The score is never used to choose judge-mode zombies or the validation sample; raters are blind to it.

Weights, the intersection factor (0.9, raised from the 0.7 in design.md so that segment > intersection > radius holds at equal distance) and the radius factor (0.8) are proposals and are not validated against the hand-checked sample yet.
