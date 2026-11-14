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

## Closed on time vs stayed fixed (demo-critical part)

The scorecard (`stats/scorecard.json`) counts closed cases that belong to an eligible original: not a transfer or a new-system Transitioned closure, and closed at least `WINDOW_DAYS` before the data ends. The on-time rate is on-time cases over cases whose `on_time` flag is known (legacy `on_time` ONTIME or OVERDUE; new-system `on_time`). The raw stayed-fixed rate is on-time cases whose incident has no possible zombie, over the same denominator, so it is never above the on-time rate. Both carry Wilson 95% intervals. Planned follow-ups and separate deaths count as not resurrected. The headline set counts headline zombies only; the "all" set counts every tier. The adjusted rate stays null until the baseline exists (credibility layer).

Sample caveat: `data/sample/sample_311.csv` is built to hold many re-report pairs, so its rates (about 70% on time, 49% stayed fixed) show that the scorecard works and are not citywide figures. The raw legacy files name the columns `on_time` and `sla_target_dt`; the pipeline also accepts the older spellings `ontime` and `target_dt`.

## Street segments and intersections (credibility; REQ-ING-SNAP)

**Snapping.** Every in-scope case is snapped to the nearest Boston Street Segments (SAM) line. Distances are measured in a local metre projection (origin 42.33 N; the error over Boston is below 0.2% of a distance). `segment_id` and `segment_snap_m` are stored for the nearest segment within 100 m. A case counts as snapped only when `segment_snap_m` is at most `SEGMENT_SNAP_M` (15 m). Ties between equally near segments go to the smallest segment ID, so a run never depends on row order. Rows that already carry a `segment_id` (the test town) are not snapped again.

**Intersections.** SAM has no node IDs. An intersection is a segment endpoint (the first or last vertex) that two or more distinct segments share, matched at 6 decimal places of latitude and longitude and at the same z-level (`F_ZLEV` for the first vertex, `T_ZLEV` for the last). An endpoint that only one segment uses is a dead end and is not an intersection. In the snapshot of 2026-11-11 the file has 19,442 segments and 11,802 intersections; 14.7% of the distinct endpoints are dead ends. Each snapped case stores the intersections within `INTERSECTION_M` (15 m) as `near_nodes`.

**Limitation.** A shared endpoint is a segment break, and not every break is a cross street: a street can be split mid-block. The intersection rule can therefore also join two cases on consecutive segments of one street when both lie within 15 m of such a break. The 15 m limit keeps this to cases that are close to each other anyway (at most 30 m apart through the node).

**When the segments file is missing.** No case is snapped, matching falls back to the radius rule only, and `status.json` records `segments: missing` with an anomaly line. The committed sample run (`make pipeline-sample`) never snaps: it needs no raw files.

## Bulk closures (credibility; REQ-BULK)

A (department, close date, template) group is a bulk closure when it has at least 50 closed in-scope cases and at least 10 times the department's usual daily count for that template. The usual daily count is the median daily closure count of that department and template over the days that have closures. The close date is the Boston local date; the template is the closure text with timestamps, dates, case IDs and numbers masked (the same key the Coroner labels use); a case with no department is grouped under "(unknown)". The flag is stored in its own `bulk_closure` field on the case, the incident and the zombie. It never replaces the Coroner label, which the planned-follow-up rule reads. It caps the label term of the confidence score at 0.5 and shows on the card. `bulk_closures.json` lists the flagged groups with their counts and ratio.

## Sensitivity runs (credibility; REQ-SENS-RUN)

The detector runs at every point of the grid: matching in {segment, radius}, `RADIUS_M` in {15, 30, 50} and `WINDOW_DAYS` in {30, 60, 90}, 18 points, with every other parameter at its default. One more run drops every case of type Street Light Other (the migration catch-all) at the default parameters. The DuckDB file holds two tables: `grid_run_index` (one row per run, with the tier totals, so a run with no zombie still appears) and `grid_runs` (zombie counts by run, tier, type family and department). In `radius` matching, segments and intersections are ignored; in `segment` matching, `RADIUS_M` only affects pairs where a case has no segment. Skeptic and confidence steps are not part of a grid run. `make pipeline --skip-grid` (the CLI flag) leaves the tables out for quick local runs.

## Payload budget (credibility; REQ-EXP-SIZE)

Autopsy cards are sharded by neighborhood and resurrection year (`cards/<neighborhood>-<year>.json`), so a phone loads only the shard it opens. Every exported `.json` file, including the stats files, gets a `.json.gz` copy that decompresses to exactly the same bytes (gzip level 9, no timestamp, so two runs write identical copies). The first view loads `status.json`, `points.json`, `stats/scorecard.json` and `stats/judge_tour.json`. Their total size before compression must stay under 3,000,000 bytes: an export over the budget raises an error before any file is written, so the previous files stay in place. The run report lists the size of every exported file and the first-view total.
