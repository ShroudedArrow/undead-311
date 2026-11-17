# Stats review: full-data run full-2 (2026-11-16)

Run full-2 is the full data (3,040,547 legacy and 90,493 new-system rows, data through 2026-11-15) on branch `fix/fulldata-2`, `data_version` `2026-11-16+b840b1f+89e078da`, four legs. It is a dry run, not the judging snapshot. Counts are a floor.

## Verdict: the placebo interval does not cover 0, so the excess is not fit to publish

The headline placebo is **-3,152 (95% interval -3,368 to -2,932)** and `status.json` carries the calibration warning. The instruction was to explain this before changing anything else, so **no estimator, cohort or matching rule was changed after seeing this result.** The per-tier population work (item b) is in; what follows is the diagnosis.

Headline excess went from -32,944 (full-1, pooled baseline) to **-9,839 (-10,521 to -9,108)** after each tier was given its own population: 18,904 observed against 28,743 expected on 251,584 eligible originals. That is still below 0, and the placebo says the baseline runs high even for closures moved away from their reports.

### Why, with numbers

I rebuilt the headline model from the final database and looked at its cohort (215,748 originals whose label is not a planned-follow-up label; the script is `reports/full-2/diag.py`, read-only). Three causes, largest first.

1. **The spot is larger than the match.** A spot is a whole street segment (or a 60 m cell), and the baseline counts every live same-family report there. The detector matches only reports within 75 m on a segment (30 m in a cell). Weighting each original's `p` by the share of the spot's other live reports that lie within the match distance of the original (75 m on a segment, 30 m in a cell; 83% on average, weighted by `p`) lowers the expected count from 24,654 to 20,401 and the cohort's deficit from -9,990 to -5,737. That is about -4,250 of the -9,990.
2. **The estimator is cautious at dense and near-regular spots.** The placebo counts any report in the spot, so it does not suffer from cause 1, and it is still -3,152. docs/METHODS.md already documents this direction: where reports are frequent, one re-report attaches to one incident only (ZD step 4), while the baseline counts every report that falls in a window, and the sliding-window share counts reports in dead stretches. A negative placebo with a negative excess means the baseline is cautious, not that the excess is inflated.
3. **What is left, roughly -2,600 (the three causes overlap, so these are not exact shares),** sits in segment spots read by the pooled family fallback (29,837 originals: observed 395, expected 1,765) and in sparse spots read by their own history (observed 11,527, expected 17,177 before the distance weighting, 14,213 after). I did not isolate it further. The pooled fallback is the clearest candidate: those are spots with under 4 windows of history, and one rate for the whole family runs high for them.

By family (tables below), street fixtures (+36) and traffic signals (+470) are the only headline families above 0.

### Read the distance-band rows with cause 1 in mind

The bands split each original's `p` by where the spot's other live reports lie, up to the match limit. `p` itself still counts the whole spot, so the bands inherit cause 1. Headline, bands 0-5, 5-15 and 15-30 m add up to +4 (-312, +342, -26). **All of the headline deficit (-9,844) is in the 30-75 m band**, which exists only on segments, where the baseline credits reports the detector rarely matches. The band rows are a diagnostic that locates the problem, not a second estimate.

### The source_unknown tier is wrong in my implementation (not a finding)

Observed 94, expected 11,271. The cohort is every core original with a planned-follow-up label (35,835), but a new-system re-report can only exist for originals closed since the new system started (2025-08-01 less the 60-day window): **2,966 of 35,883 originals**. For the other 32,917 the population is empty and the expected count comes from the pooled fallback, which is meaningless there (33,661 of 35,835 used it). Do not read this tier's excess. A cohort rule that says "an original is in a tier's cohort only when its window can contain a report of that tier's population" fixes it; it depends on the label, not on the outcome. I did not apply it.

### The city_rereport tier is positive for a known reason

+7,218 (6,309 to 8,159): observed 33,022, expected 25,803. The 0-5 m band alone is +11,592 and 13,304 of the re-reports opened within an hour of the closure (crew work records, ZD step 6, ops#29). A crew record at the same spot right after a closure is not a coincidence, so a positive excess is what this tier should show. It is outside the headline.

## Other results

- Zombies: headline 19,112, source_unknown 98, city_rereport 33,022, sensitivity 202. full-1 had 20,766, 85, 37,390, 202. Planned follow-ups kept out rose from 2,137 to 4,912. The cause is the Coroner: with 99.5% of closures labeled, many closures that were `other` are now `made_safe_temporary`, `planned_followup` or `referred`, and a city re-report after one of those is a planned follow-up, not a zombie. Please confirm you accept that shift in the headline (-1,654) before it is published.
- Coroner coverage: 63.7% -> **99.52%** of 315,607 closed in-scope cases (1,528 unlabeled, 821 of them with empty closure text). By source: label table, new-system closure code, leading phrase (see `coverage.json`; the run report has `labeled_by_*`).
- Coroner accuracy: `make coroner-eval` found no `data/labels/coroner_hand_labels.csv`, so the 200 hand labels were **not scored** (they are not in the repository or on any branch). On a seeded random draw of 200 full-data closures that I labeled as the Coroner (`data/labels/coroner_random200.csv`), the pipeline rule agrees on **180 of 200 (90.0%, Wilson 95% interval 85.1% to 93.4%)**: label table 124 of 126, closure code 0 of 2, leading phrase 56 of 72 (77.8%). I wrote those labels and the draw was not independent of me, so it measures the rule against my reading, not against a person's. The leading phrase rule agrees with the older label table on 84% of its 3,926 templates (a harder set than the long tail).
- Departments: the legacy codes and new-system names are one row each (PWDx now holds the 173,848 headline-cohort originals of both systems; there is no separate "Public Works Department (PWD)" row). In-scope values kept under their own code because they are not in the CRM Value Code Index and no mapping could be found: BHA 281, ONS 157, DND 16, GEN 9, GRNi 4, ECON 1, Test 1 (flagged in `department_crosswalk.csv`). Not found anywhere: what BHA, ONS, DND, GEN, GRNi and ECON stand for. INFO is "Information Channel (Not a department)" in the Index. Cases with no department (new system, 44 in scope) stay empty.
- Payload: first view **327,681 B gzip** (2,271,641 B raw) against the 3,000,000 B gzip budget and the 8 MB raw ceiling; largest file `points/city_rereport.json` at 478,427 B gzip; 668 files, 116.5 MB raw. No file is near 2 MB compressed, and nothing needed the dry-run override.
- `status.json` anomalies: the city-share note and the flagged departments. No DRY RUN ONLY anomaly, so these exports can be published.

## Questions for you

1. Do you want the cohort-availability rule for source_unknown (and a rerun)? It changes only that tier's rows.
2. For causes 1 and 3: matching a spot's baseline to the match area (count only reports within the match distance) would address most of the -4,250. That changes methods.md (the spot definition for the baseline), which an agent cannot edit. Your call.
3. Is a headline shift from 20,766 to 19,112 acceptable on account of the new Coroner labels?
4. Where are the 200 hand labels (`data/labels/coroner_hand_labels.csv`)?

# Tables

## Per tier

| tier | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| headline | 18,904 | 28,743 | -9,839 (-10,521 to -9,109) | 251,584 | -8,065 |
| source_unknown | 94 | 11,271 | -11,177 (-12,258 to -10,202) | 35,835 | -11,093 |
| city_rereport | 33,022 | 25,803 | +7,219 (+6,310 to +8,159) | 215,748 | +1,610 |
| sensitivity | 56 | 67 | -11 (-25 to +4) | 430 | -6 |

## Per family and tier


**headline**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| pavement_marking | 5 | 11 | -6 (-11 to -1) | 1,594 | -6 |
| pothole_roadway | 9,185 | 13,990 | -4,805 (-5,324 to -4,327) | 96,891 | -3,713 |
| sidewalk | 3,284 | 4,520 | -1,236 (-1,480 to -1,006) | 34,247 | -914 |
| sign | 2,482 | 4,249 | -1,767 (-1,962 to -1,578) | 57,168 | -1,495 |
| street_fixture | 59 | 23 | +36 (+20 to +54) | 3,104 | +36 |
| streetlight | 3,376 | 5,907 | -2,531 (-2,908 to -2,194) | 55,652 | -2,290 |
| traffic_signal | 513 | 43 | +470 (+384 to +556) | 2,928 | +317 |

**source_unknown**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| pavement_marking | 0 | 0 | -0 (-0 to -0) | 353 | -0 |
| pothole_roadway | 73 | 4,347 | -4,274 (-4,811 to -3,758) | 12,336 | -4,262 |
| sidewalk | 15 | 4,789 | -4,774 (-5,225 to -4,316) | 14,518 | -4,719 |
| sign | 1 | 690 | -689 (-1,494 to +1) | 2,091 | -689 |
| street_fixture | 1 | 0 | +1 (-0 to +3) | 1,451 | +1 |
| streetlight | 4 | 1,444 | -1,440 (-1,573 to -1,305) | 4,924 | -1,424 |
| traffic_signal | 0 | 0 | -0 (-0 to -0) | 162 | -0 |

**city_rereport**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| pavement_marking | 28 | 13 | +15 (+4 to +28) | 1,240 | +15 |
| pothole_roadway | 21,521 | 14,284 | +7,237 (+6,433 to +8,000) | 84,555 | +1,204 |
| sidewalk | 1,334 | 1,798 | -464 (-635 to -285) | 19,729 | -219 |
| sign | 4,166 | 4,922 | -756 (-963 to -556) | 55,077 | -563 |
| street_fixture | 46 | 45 | +1 (-13 to +17) | 1,653 | -0 |
| streetlight | 5,635 | 4,711 | +924 (+687 to +1,187) | 50,728 | +935 |
| traffic_signal | 292 | 32 | +260 (+214 to +307) | 2,766 | +237 |

**sensitivity**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| streetlight | 56 | 67 | -11 (-24 to +5) | 430 | -6 |

## Per match-distance band and tier


**headline**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 11,121 | 11,433 | -312 (-636 to +11) | 251,584 | -440 |
| 5-15 m | 2,205 | 1,863 | +342 (+219 to +465) | 251,584 | +264 |
| 15-30 m | 4,279 | 4,304 | -25 (-196 to +162) | 251,584 | +6 |
| 30-75 m | 1,299 | 11,143 | -9,844 (-10,337 to -9,338) | 251,584 | -7,895 |

**source_unknown**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 17 | 997 | -980 (-1,250 to -757) | 35,835 | -977 |
| 5-15 m | 40 | 1,430 | -1,390 (-1,823 to -1,062) | 35,835 | -1,381 |
| 15-30 m | 30 | 3,093 | -3,063 (-3,658 to -2,578) | 35,835 | -3,036 |
| 30-75 m | 7 | 5,751 | -5,744 (-6,579 to -4,943) | 35,835 | -5,698 |

**city_rereport**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 22,294 | 10,702 | +11,592 (+10,796 to +12,466) | 215,748 | +4,069 |
| 5-15 m | 2,839 | 1,466 | +1,373 (+1,223 to +1,532) | 215,748 | +837 |
| 15-30 m | 6,210 | 3,609 | +2,601 (+2,403 to +2,805) | 215,748 | +1,478 |
| 30-75 m | 1,679 | 10,026 | -8,347 (-8,828 to -7,883) | 215,748 | -4,775 |

**sensitivity**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 30 | 17 | +13 (+3 to +23) | 430 | +7 |
| 5-15 m | 6 | 4 | +2 (-3 to +7) | 430 | +3 |
| 15-30 m | 15 | 12 | +3 (-4 to +12) | 430 | +3 |
| 30-75 m | 5 | 33 | -28 (-35 to -22) | 430 | -19 |

## Per department and tier


**headline** (departments with at least 50 originals)

| department | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| BTDT | 3,033 | 4,378 | -1,345 (-1,554 to -1,136) | 61,883 | -1,205 |
| BWSC | 319 | 403 | -84 (-121 to -45) | 4,785 | -57 |
| DISB | 3 | 3 | -0 (-3 to +4) | 67 | -0 |
| INFO | 908 | 963 | -55 (-121 to +14) | 8,799 | -53 |
| ISD | 66 | 84 | -18 (-44 to +3) | 564 | -9 |
| PARK | 112 | 157 | -45 (-69 to -21) | 1,525 | -36 |
| PROP | 0 | 2 | -2 (-3 to -1) | 54 | -2 |
| PWDx | 14,458 | 22,748 | -8,290 (-8,936 to -7,660) | 173,848 | -6,703 |

**source_unknown** (departments with at least 50 originals)

| department | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| BTDT | 0 | 607 | -607 (-1,201 to -79) | 2,318 | -606 |
| BWSC | 1 | 175 | -174 (-195 to -156) | 1,124 | -173 |
| INFO | 9 | 1,338 | -1,329 (-1,497 to -1,167) | 4,121 | -1,326 |
| ISD | 0 | 32 | -32 (-36 to -27) | 99 | -32 |
| PARK | 0 | 126 | -126 (-144 to -112) | 380 | -125 |
| PWDx | 83 | 8,987 | -8,904 (-9,493 to -8,289) | 27,773 | -8,826 |

**city_rereport** (departments with at least 50 originals)

| department | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| BTDT | 4,558 | 5,027 | -469 (-677 to -269) | 59,564 | -303 |
| BWSC | 266 | 347 | -81 (-112 to -44) | 3,661 | -48 |
| DISB | 1 | 4 | -3 (-4 to +0) | 55 | -2 |
| INFO | 222 | 359 | -137 (-174 to -99) | 4,678 | -80 |
| ISD | 31 | 52 | -21 (-49 to -1) | 465 | -21 |
| PARK | 56 | 87 | -31 (-46 to -15) | 1,145 | -22 |
| PROP | 2 | 2 | +0 (-2 to +3) | 52 | +0 |
| PWDx | 27,879 | 19,921 | +7,958 (+7,055 to +8,921) | 146,075 | +2,083 |

## Placebo and shift test per tier

| tier | placebo excess (95% interval) | warning | shift: observed | shift mean (2.5% to 97.5%) | detector count |
|---|---|---|---|---|---|
| city_rereport | -4,773 (-5,040 to -4,522) | yes | 46,196 | 21,792 (21,312 to 22,283) | 33,022 |
| headline | -3,152 (-3,368 to -2,932) | yes | 26,166 | 19,621 (19,224 to 20,027) | 19,112 |
| sensitivity | -18 (-24 to -12) | yes | 92 | 55 (42 to 69) | 202 |
| source_unknown | -1,200 (-1,368 to -1,035) | yes | 769 | 2,353 (2,313 to 2,391) | 98 |
