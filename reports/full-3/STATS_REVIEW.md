# Stats review: full-data run full-3 (2026-11-17)

full-3 is a fresh full-data run on branch `fix/fulldata-2` with the match-area baseline (methods.md, re-synced 2026-11-16) and the source_unknown cohort rule. Inputs are the same files as full-2 (download 2026-11-16, data through 2026-11-15); `data_version` `2026-11-16+5b76337+89e078da`. Five legs: the grid now takes about 9.5 minutes per group because every grid point builds its match areas. It is a dry run, not the judging snapshot. Counts are a floor.

## Verdict: the headline placebo still excludes 0, so the excess is not shown

| tier | placebo excess (95% interval) | covers 0 |
|---|---|---|
| headline | -3,322 (-3,504 to -3,110) | no |
| source_unknown | -115 (-157 to -74) | no |
| city_rereport | -5,012 (-5,246 to -4,789) | no |
| sensitivity | -22 (-29 to -15) | no |

As you asked, I did not tune anything after seeing this. Per methods.md the site now withholds the excess wherever it appears (methods page table, scorecard lines, slider row) when the headline placebo interval does not cover 0, and the methods page shows the placebo instead (`excessShown` in `web/src/lib/methods.ts`). The committed sample data's placebo covers 0 (+3.6, -22.3 to +26.2), so the sample still shows its excess; full-data exports like full-3 would not.

## What changed from full-2

- Headline excess: -9,839 (full-2) to **-4,928 (-5,377 to -4,486)**; 18,904 observed against 23,832 expected on 251,583 originals. The match-area baseline removed about half of the deficit, roughly the -4,250 that the full-2 review attributed to the spot being larger than the match.
- The placebo did not move (-3,152 to -3,322). That is consistent with the full-2 diagnosis: the placebo was never affected by the spot size, because a shifted closure's hits are counted in the same area as its `p`. So the area fix corrected the excess but not the calibration.
- source_unknown: the cohort is now 2,539 originals whose window reaches the new system (was 35,835), and its expected count fell from 11,271 to 865. It still runs high (94 observed, 2,366 of 2,539 on the pooled fallback).
- More pooled fallbacks: 48,079 headline-cohort originals use the pooled family rate (34,463 in full-2), because a match area has a shorter history than a whole segment.
- Zombie counts are unchanged (headline 19,112, source_unknown 98, city_rereport 33,022, sensitivity 202): the baseline never changes detection. One Test-department case is now excluded as `test_data`, so the in-scope total is 388,482.

## Why the placebo is still below 0 (not isolated further)

These are the two remaining explanations in METHODS.md, with full-3 numbers. I did not run separate tests to split them.
1. **A report is counted for every original whose area holds it, but attached to one incident.** Unshifted, 20,644 headline-cohort originals have a same-area report in their window (the shift test's `observed`), while the detector attaches 18,904. Match areas overlap (median 5 cases, 95th percentile 36), so one report falls in several originals' windows. The baseline and the placebo count it for each of them, while attribution (ZD step 4) gives it to the most recent incident. The distance bands show the same thing: headline 0-5 m is -223 (-518 to +61) and the deficit grows with distance, to -2,955 at 30-75 m, where a report is most likely to belong to a closer incident.
2. **The dense-spot estimator is cautious** (sliding-window share, reports in dead stretches counted). It is documented in METHODS.md with null towns, and it is where the placebo reads below 0 on null towns too.

The positive city_rereport excess (+12,559) is the 0-5 m band (+12,116): crew work records filed at the spot right after a closure (13,304 within 1 hour), which are not coincidences.

## Open point for you

The scorecard's adjusted stayed-fixed rate subtracts expected coincidences, so it uses the same baseline the placebo calls uncalibrated. methods.md's rule names the excess only, so I left the adjusted rate on the site. Tell me if it should be withheld too.

# Tables

## Per tier

| tier | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| headline | 18,904 | 23,832 | -4,928 (-5,377 to -4,486) | 251,583 | -4,535 |
| source_unknown | 94 | 865 | -771 (-935 to -609) | 2,539 | -768 |
| city_rereport | 33,022 | 20,463 | +12,559 (+11,607 to +13,577) | 215,747 | +5,097 |
| sensitivity | 56 | 63 | -7 (-23 to +9) | 430 | -8 |

## Per family and tier


**headline**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| pavement_marking | 5 | 13 | -8 (-14 to -2) | 1,594 | -8 |
| pothole_roadway | 9,185 | 11,497 | -2,312 (-2,594 to -1,995) | 96,890 | -2,127 |
| sidewalk | 3,284 | 3,612 | -328 (-495 to -160) | 34,247 | -264 |
| sign | 2,482 | 3,746 | -1,264 (-1,421 to -1,108) | 57,168 | -1,051 |
| street_fixture | 59 | 23 | +36 (+21 to +53) | 3,104 | +36 |
| streetlight | 3,376 | 4,887 | -1,511 (-1,708 to -1,318) | 55,652 | -1,419 |
| traffic_signal | 513 | 53 | +460 (+384 to +545) | 2,928 | +299 |

**source_unknown**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| pothole_roadway | 73 | 698 | -625 (-759 to -484) | 1,623 | -624 |
| sidewalk | 15 | 150 | -135 (-194 to -74) | 564 | -135 |
| sign | 1 | 0 | +1 (-0 to +3) | 185 | +1 |
| street_fixture | 1 | 0 | +1 (-0 to +3) | 96 | +1 |
| streetlight | 4 | 17 | -13 (-20 to -6) | 44 | -11 |
| traffic_signal | 0 | 0 | -0 (-0 to -0) | 27 | -0 |

**city_rereport**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| pavement_marking | 28 | 13 | +15 (+4 to +27) | 1,240 | +15 |
| pothole_roadway | 21,521 | 10,950 | +10,571 (+9,691 to +11,490) | 84,554 | +3,169 |
| sidewalk | 1,334 | 1,461 | -127 (-258 to +2) | 19,729 | +0 |
| sign | 4,166 | 4,123 | +43 (-117 to +200) | 55,077 | +168 |
| street_fixture | 46 | 35 | +11 (-3 to +25) | 1,653 | +9 |
| streetlight | 5,635 | 3,834 | +1,801 (+1,611 to +1,989) | 50,728 | +1,518 |
| traffic_signal | 292 | 47 | +245 (+195 to +287) | 2,766 | +218 |

**sensitivity**

| family | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| streetlight | 56 | 63 | -7 (-23 to +8) | 430 | -8 |

## Per match-distance band and tier


**headline**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 11,121 | 11,344 | -223 (-518 to +61) | 251,583 | -310 |
| 5-15 m | 2,205 | 2,796 | -591 (-722 to -472) | 251,583 | -589 |
| 15-30 m | 4,279 | 5,438 | -1,159 (-1,336 to -974) | 251,583 | -1,041 |
| 30-75 m | 1,299 | 4,254 | -2,955 (-3,109 to -2,811) | 251,583 | -2,594 |

**source_unknown**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 17 | 196 | -179 (-275 to -95) | 2,539 | -176 |
| 5-15 m | 40 | 222 | -182 (-280 to -95) | 2,539 | -186 |
| 15-30 m | 30 | 322 | -292 (-395 to -185) | 2,539 | -290 |
| 30-75 m | 7 | 125 | -118 (-198 to -46) | 2,539 | -117 |

**city_rereport**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 22,294 | 10,178 | +12,116 (+11,317 to +12,971) | 215,747 | +5,297 |
| 5-15 m | 2,839 | 2,242 | +597 (+452 to +754) | 215,747 | +224 |
| 15-30 m | 6,210 | 4,483 | +1,727 (+1,511 to +1,951) | 215,747 | +894 |
| 30-75 m | 1,679 | 3,561 | -1,882 (-2,052 to -1,722) | 215,747 | -1,318 |

**sensitivity**

| band | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| 0-5 m | 30 | 24 | +6 (-7 to +19) | 430 | -0 |
| 5-15 m | 6 | 9 | -3 (-7 to +2) | 430 | -2 |
| 15-30 m | 15 | 15 | +0 (-7 to +8) | 430 | +1 |
| 30-75 m | 5 | 16 | -11 (-16 to -5) | 430 | -8 |

## Per department and tier


**headline** (departments with at least 50 originals)

| department | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| BTDT | 3,033 | 3,894 | -861 (-1,031 to -673) | 61,883 | -785 |
| BWSC | 319 | 335 | -16 (-50 to +20) | 4,785 | -3 |
| DISB | 3 | 2 | +1 (-2 to +4) | 67 | +1 |
| INFO | 908 | 816 | +92 (+27 to +162) | 8,799 | +55 |
| ISD | 66 | 67 | -1 (-17 to +16) | 564 | -1 |
| PARK | 112 | 120 | -8 (-28 to +12) | 1,525 | -13 |
| PROP | 0 | 1 | -1 (-2 to -1) | 54 | -1 |
| PWDx | 14,458 | 18,591 | -4,133 (-4,517 to -3,749) | 173,848 | -3,786 |

**source_unknown** (departments with at least 50 originals)

| department | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| BTDT | 0 | 4 | -4 (-7 to -2) | 84 | -4 |
| BWSC | 1 | 19 | -18 (-25 to -12) | 101 | -18 |
| INFO | 9 | 209 | -200 (-244 to -157) | 673 | -199 |
| PWDx | 83 | 629 | -546 (-666 to -436) | 1,663 | -544 |

**city_rereport** (departments with at least 50 originals)

| department | observed | expected | excess (95% interval) | originals | excess without bursty spots |
|---|---|---|---|---|---|
| BTDT | 4,558 | 4,245 | +313 (+152 to +487) | 59,564 | +409 |
| BWSC | 266 | 276 | -10 (-41 to +24) | 3,661 | -10 |
| DISB | 1 | 3 | -2 (-5 to +1) | 55 | -2 |
| INFO | 222 | 317 | -95 (-127 to -60) | 4,678 | -67 |
| ISD | 31 | 47 | -16 (-41 to +2) | 465 | -18 |
| PARK | 56 | 69 | -13 (-26 to +1) | 1,145 | -10 |
| PROP | 2 | 1 | +1 (-1 to +4) | 52 | +1 |
| PWDx | 27,879 | 15,501 | +12,378 (+11,443 to +13,421) | 146,075 | +4,791 |

## Placebo and shift test per tier

| tier | placebo excess (95% interval) | warning | shift: observed | shift mean (2.5% to 97.5%) | detector count |
|---|---|---|---|---|---|
| city_rereport | -5,012 (-5,246 to -4,789) | yes | 38,808 | 16,596 (16,226 to 16,962) | 33,022 |
| headline | -3,322 (-3,504 to -3,110) | yes | 20,644 | 14,877 (14,561 to 15,199) | 19,112 |
| sensitivity | -22 (-29 to -15) | yes | 65 | 42 (30 to 54) | 202 |
| source_unknown | -115 (-157 to -73) | yes | 135 | 160 (149 to 171) | 98 |
