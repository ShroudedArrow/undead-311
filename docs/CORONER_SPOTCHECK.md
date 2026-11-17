# Coroner spot check (20 rows)

For the owner. `data/labels/coroner_random200.csv` is the Coroner's evaluation set: 200 closed in-scope cases drawn at random from the full data (seed 311) and labeled by the Coroner agent. These 20 rows are drawn from it with `random.Random(311).sample(range(200), 20)`, sorted by position in the file, so the same rows come out every time.

Fill the last column with `y`, or `n` and the label you would give. Allowed labels: resolved, noted, invalid, duplicate, referred, made_safe_temporary, planned_followup, bulk_backlog, other. The text is the closure text after the personal-information scrub; a case's `system` is `legacy` or `new`, and a new-system case also has a closure code.

Owner review 2026-11-17: 19 of 20 agree; row 3 is `made_safe_temporary`, not `resolved` (see docs/DECISIONS.md).

| # | case id | system | closure code | closure text | Coroner label | owner agrees? (y/n, correct label) |
|---|---|---|---|---|---|---|
| 1 | 101001411612 | legacy |  | Case Closed. Closed date : 2015-06-17 13:07:58.62 Internal Case Performed by Highway Maintenance crew. | resolved | y |
| 2 | 101001523217 | legacy |  | Case Closed. Closed date : 2015-10-21 13:45:36.05 Case Resolved Sidewalk repaired 10/2015 [removed] | resolved | y |
| 3 | 101001603144 | legacy |  | Case Closed. Closed date : 2015-10-02 10:11:33.94 Case Noted picked up sign | resolved | n made_safe_temporary |
| 4 | 101001799964 | legacy |  | Case Closed. Closed date : 2016-06-10 15:35:49.71 Case Resolved twin acorn was turned to proper position. w/o completed. [removed] | resolved | y |
| 5 | 101002079163 | legacy |  | Case Closed. Closed date : 2017-07-20 14:16:53.99 Case Resolved | resolved | y |
| 6 | 101002279881 | legacy |  | Case Closed. Closed date : 2017-12-07 12:43:46.547 Case Resolved | resolved | y |
| 7 | 101002328720 | legacy |  | Case Closed. Closed date : 2018-01-16 12:22:47.013 Case Resolved Pothole patched at said location | resolved | y |
| 8 | 101002363900 | legacy |  | Case Closed. Closed date : 2018-02-12 14:32:55.723 Case Resolved Dear Constituent A Boston Public Works crew in the interest of public safety placed a barrel over an exposed area of Private Alley 505 where a catch basin cover had fallen in. The Boston Public Works is not responsible for the maintenance upkeep of private ways Public Works then called BWSC to send a crew out right away. T | made_safe_temporary | y |
| 9 | 101002396513 | legacy |  | Case Closed. Closed date : 2018-03-15 10:18:40.713 Case Resolved Marked completed at case creation | resolved | y |
| 10 | 101002479138 | legacy |  | Case Closed. Closed date : 2018-05-21 08:41:12.12 Case Resolved work complete | resolved | y |
| 11 | 101002586307 | legacy |  | Case Closed. Closed date : 2019-06-10 13:50:15.093 Case Resolved | resolved | y |
| 12 | 101003008071 | legacy |  | Case Closed. Closed date : 2019-08-29 20:15:27.29 Case Noted eversource underground issue | referred | y |
| 13 | 101003048010 | legacy |  | Case Closed. Closed date : 2019-09-25 08:26:32.397 Case Noted Contractor has been notified to properly place signs in the area. For further information please call Chief Engineer [removed] at [removed] | referred | y |
| 14 | 101003201073 | legacy |  | Case Closed. Closed date : 2020-02-24 07:47:08.293 Case Resolved Marked completed at case creation | resolved | y |
| 15 | 101003883900 | legacy |  | Case Closed. Closed date : 2021-07-29 12:46:56.8 Case Invalid | invalid | y |
| 16 | 101004148919 | legacy |  | Case Closed. Closed date : 2022-01-28 14:44:46.127 Case Resolved PICKED UP AND MADE SAFE DAMAGED POLECAPPED CONDUIT CUT IN PULL BOX AND BOLTED DOWNCONE FOR SAFETY LSO BACK FILLED SUB BASE TO GRADE [removed] | made_safe_temporary | y |
| 17 | 101004623670 | legacy |  | Case Closed. Closed date : Tue Jan 10 14:34:59 EST 2023 Resolved | resolved | y |
| 18 | 101006021893 | legacy |  | Case Closed. Closed date : 2025-06-17 13:38:28.673 Case Resolved | resolved | y |
| 19 | 101006212356 | legacy |  | Case Closed. Closed date : 2025-09-02 11:37:34.88 Case Resolved Cleaned globe and remantled. GG PG | resolved | y |
| 20 | 101006560361 | legacy |  | Case Closed Case Resolved Patched. | resolved | y |
