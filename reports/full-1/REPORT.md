# Full-data dry run full-1 (2026-11-16)

## What this is
A dry run on all of the data, not the judging snapshot (that is Nov 20). Downloaded 2026-11-16, data through 2026-11-15, `data_version` `2026-11-16+4aeb414+89e078da`. The export ran with the dry-run-only override (owner decision, option D): `points.json` is over the 3 MB first-view budget, and `status.json` records that as a `DRY RUN ONLY` anomaly. Do not deploy these files.

## Inputs changed since the 2026-11-12 hashes
- `311_2026.csv`: same size (107,894,233 bytes), new hash (rows edited in place).
- `311_new_system.csv`: 31,026,342 to 31,923,853 bytes.
- The other 13 files are byte-identical. Full list: `download-report.json`.

## Rows
3,040,547 legacy and 90,493 new-system rows; 388,483 in scope after cleaning (exclusions: unlisted type 1,877,683; excluded type 861,963; no coordinates 2,119; placeholder 792). 233,615 cases snapped to a street segment, 154,868 did not. Mirror pairs excluded 22, transferred originals 732, mirror copies merged 36.

## Possible zombies (counts are a floor)
| Tier | Count |
|---|---|
| headline | 20,766 |
| source_unknown | 85 |
| city_rereport | 37,390 |
| sensitivity | 202 |

64.3% of headline-plus-city re-reports are city-originated; 13,982 of those opened within 1 h of the closure. Planned follow-ups kept out: 2,137. Running without Street Light Other changes the headline count from 20,766 to 20,775.

## Stayed fixed vs on time (citywide)
- On time: 0.658 (95% interval 0.657 to 0.660), n = 309,467.
- Stayed fixed, raw, headline tier: 0.609 (0.607 to 0.611); adjusted: 0.622 (0.620 to 0.624).
- Stayed fixed, raw, all tiers: 0.500 (0.499 to 0.502).

## Excess, placebo and shift test: NOT FIT TO PUBLISH
Every headline family except traffic signals has a large negative excess, and the placebo fails:
- Headline excess, summed over families: observed 20,555 eligible originals that resurrected vs 53,499 expected, excess -32,944. Without bursty spots: 12,563 observed vs 30,031 expected, excess -17,468. Intervals are per family (`stats/excess.json`) and cannot be added.
- All tiers: pothole_roadway +8,019 (7,119 to 8,939), traffic_signal +756, streetlight +248 (-156 to 661), sidewalk -2,866, sign -1,642.
- Placebo (10 time-shifted runs): excess -8,528 (-8,841 to -8,201). It should be near 0; `status.json` carries the calibration warning.
- Shift test: observed 83,931 vs a shifted mean of 46,177 (45,544 to 46,808), 1,000 runs, seed 311.

The headline and city tiers are compared with one expected count that includes every same-family report, city crew reports included. That is the likely cause; fix/fulldata-2 restricts the baseline to the same population per tier.

## Departments and neighborhoods
`stats/groups.json` ranks resurrection rates (lower is better), shrunk toward the citywide 0.072, with 95% intervals. Stayed-fixed rates are exported per family only, not per group.
- Lowest departments: PROP 0.041 (0.015 to 0.080, n = 59), BTDT 0.048 (0.047 to 0.050, n = 70,927), DISB 0.058 (0.028 to 0.099, n = 87).
- Highest departments: PWD (new-system name) 0.143 (0.133 to 0.153, n = 4,723), INFO 0.103 (0.097 to 0.109, n = 10,076), Parks & Recreation 0.090 (0.041 to 0.154, n = 18).
- Lowest neighborhoods: Hyde Park 0.037 (0.034 to 0.040), West Roxbury 0.040 (0.037 to 0.044), East Boston 0.044 (0.041 to 0.046).
- Highest neighborhoods: Back Bay 0.133 (0.128 to 0.138), South End 0.116 (0.111 to 0.121), Beacon Hill 0.109 (0.103 to 0.114).
- Read with reporting intensity: Back Bay has 549 reports per km of street, Hyde Park 123. The department names come from two vocabularies (legacy codes, new-system names), so PWD and the legacy PWD codes are separate rows.

## Personal-information scrub (exported free text)
phone 2,715; email 1,053; digit run 619; context name 525; honorific name 17.

## Coroner coverage
63.7% of 315,607 closed in-scope cases (legacy 63.0%, new system 88.4%); 114,437 unlabeled across 78,211 distinct templates. The 300 largest (`unlabeled_templates_top300.csv`) hold 13,912 cases; labeling them all would reach 68.1%.

## Sample notice
`status.json` has `dataset: full` and a `data_version` that does not start with `fixture-`, so the sample notice and the stand-in notice both switch off with these files (by the rules in `web/src/lib/dataAsOf.ts`; not checked in a browser).

## Stages
Committed stages ran once (legs 1 to 5); the unmarked steps rerun on each leg, so their times are from the final leg.

| Stage | Seconds | Peak memory (MB) | Kind | Finished (UTC) |
|---|---|---|---|---|
| load | 15.1 | 3,872 | committed | 2026-11-16T04:42:29Z |
| normalize | 74.9 | 4,337 | committed | 2026-11-16T04:43:48Z |
| crosswalk | 2.5 | 3,441 | committed | 2026-11-16T04:43:53Z |
| clean | 2.4 | 3,421 | committed | 2026-11-16T04:43:58Z |
| snap | 135.5 | 2,517 | committed | 2026-11-16T04:46:18Z |
| neighborhoods | 2.1 | 2,155 | committed | 2026-11-16T04:46:21Z |
| templates | 4.4 | 985 | unmarked, final leg | 2026-11-16T16:02:34Z |
| coroner | 116.2 | 2,563 | committed | 2026-11-16T04:48:22Z |
| bulk | 45.0 | 2,607 | committed | 2026-11-16T04:49:08Z |
| detect | 193.0 | 1,650 | unmarked, final leg | 2026-11-16T16:05:48Z |
| grid-segment-r15 | 324.4 | 2,215 | committed | 2026-11-16T05:25:23Z |
| grid-segment-r30 | 326.6 | 2,256 | committed | 2026-11-16T05:30:51Z |
| grid-segment-r50 | 333.7 | 2,321 | committed | 2026-11-16T05:36:25Z |
| grid-radius-r15 | 338.4 | 2,258 | committed | 2026-11-16T05:42:04Z |
| grid-radius-r30 | 330.3 | 2,233 | committed | 2026-11-16T05:50:56Z |
| grid-radius-r50 | 330.4 | 2,271 | committed | 2026-11-16T05:56:28Z |
| grid-no-street-light-other | 229.4 | 2,213 | committed | 2026-11-16T15:42:35Z |
| grid | 1.0 | 1,658 | committed | 2026-11-16T15:46:14Z |
| baselines | 19.2 | 1,759 | unmarked, final leg | 2026-11-16T16:06:09Z |
| skeptic | 3.9 | 1,759 | unmarked, final leg | 2026-11-16T16:06:13Z |
| stats | 451.8 | 2,754 | unmarked, final leg | 2026-11-16T16:13:46Z |
| export | 282.3 | 2,189 | unmarked, final leg | 2026-11-16T16:18:29Z |

Sum of stage times: 3,562 s (59 min).

Heaviest process memory: 4.3 GB (normalize). DuckDB limit 20 GB (65% of RAM), 8 threads, spill under $DATA_DIR/tmp (never used).

## Files (largest first; none over 50 MB)
| File | Bytes |
|---|---|
| web/public/data/zombies.json | 40,563,463 |
| web/public/data/incidents.json | 17,205,266 |
| web/public/data/points.json | 6,311,046 |
| web/public/data/stats/trends.json | 792,011 |
| web/public/data/stats/survival.json | 601,841 |
| web/public/data/separate_deaths.json | 563,257 |
| web/public/data/exclusions.json | 194,047 |
| web/public/data/stats/funnel.json | 184,514 |
| web/public/data/repeat_offenders.json | 176,431 |
| web/public/data/stats/excess.json | 41,382 |
| web/public/data/stats/groups.json | 36,349 |
| web/public/data/bulk_closures.json | 19,910 |
| web/public/data/stats/scorecard.json | 15,195 |
| web/public/data/stats/temporary_fixes.json | 8,472 |
| web/public/data/stats/sensitivity_grid.json | 6,233 |
| web/public/data/status.json | 1,148 |
| web/public/data/stats/validation.json | 295 |
| web/public/data/stats/judge_tour.json | 281 |
| web/public/data/stats/stats_status.json | 204 |
| web/public/data/.gitkeep | 0 |
| web/public/data/cards/ (215 shards) | 60,163,184 (largest west-roxbury-2015.json 1,315,419) |

Total served data: 126,884,529 bytes.
