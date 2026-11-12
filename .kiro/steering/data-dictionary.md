---
inclusion: auto
name: data-dictionary
description: Boston 311 dataset fields, case-type families, closure-reason patterns. Use when writing ingest, detection, or any code that reads 311 data.
---
# Boston 311 data dictionary

Status: VERIFIED by the kickoff on 2026-11-12

Counts below come from DuckDB tables `raw_legacy` and `raw_new` (snapshot in `data/SNAPSHOT.md`). Re-verify when the schema changes.

## Source
Analyze Boston dataset "311 Service Requests" (yearly CSV resources, updated daily). License: Open Data Commons PDDL. Use the dataset's **CRM Value Codex** PDF to interpret codes.

## Verified file inventory (snapshot 2026-11-12)
- Legacy yearly CSVs 2015-2026 (2011-2014 exist but are not downloaded): 3,040,547 rows, 29 columns plus `geom_4326`, all with `case_enquiry_id` unique within a year. The 2026 file is still growing, so legacy cases continue after Oct 2025.
- One NEW SYSTEM CSV: 87,951 rows opened 2025-08-01 to 2026-11-11 (`case_id` like `BCS-00256693`). There is no separate Jan-Oct 2025 legacy file; 2025 is one legacy file.
- No id overlap between systems (legacy ids are numeric `1010...`). The two systems overlap in time (Aug 2025 on), so cross-system matching is by location/time/type only.

## The 2025 system change
The 311 system changed in 2025 and **field names differ** (e.g., `open_dt` → `open_date`). The verified inventory is: yearly legacy files 2015-2026 (the 2025 and 2026 legacy files keep growing after the change) and one new-system file (opened 2025-08-01 onward, small until about June 2026). There is no separate Jan-Oct 2025 legacy file. The ingest layer maps both to the normalized schema and records `system`. The raw snapshot is pinned in `data/SNAPSHOT.md`; the Python version is pinned to 3.11 in `.python-version`.

## Time zones (corrected)
The new-system `open_date`/`close_date` strings end in `+00` but are Boston wall-clock time, not UTC. An earlier version of this file said to convert new-system times from UTC; that instruction was wrong.
Evidence: (a) 1,373 legacy cases closed with "Resubmitted as / See new case BCS-N" were re-created in the new system; the new case's naive `open_date` minus the legacy naive `closed_dt` has median -2.6 minutes (p5 -14.7 min, p95 -1.1 min) and the monthly median stays at -0.03 to -0.06 hours in every month from Aug 2025 to Nov 2026, in both daylight and standard time (if `+00` were UTC the gap would be 4 h in summer and 5 h in winter); (b) the hour-of-day histogram of new-system `open_date` peaks at 8-9 (business hours) like legacy; true UTC would peak at 12-14.
Normalization (`pipeline/undead311/ingest/times.py`): take the naive wall-clock digits (ignore `+00`), interpret as America/New_York, and store both UTC and local. Fall-back hour (01:00-01:59 on the first Sunday of November) is ambiguous: use the first occurrence (EDT) and set `local_ambiguous`. Spring-forward gap (02:00-02:59, second Sunday of March) is nonexistent: shift forward and flag it. In-scope rows in the ambiguous hour: 9 legacy and 1 new; in the gap: 0.

## Source channel (`source`)
Known legacy values: Constituent Call, Citizens Connect App, City Worker App, Self Service, Employee Generated, Twitter, Maximo Integration. City-originated values (Employee Generated, City Worker App, Maximo Integration) matter for planned follow-ups (see zombie-definition.md).

## VERIFIED legacy vs. new system field comparison
| Normalized | Legacy column | New-system column | Difference / verified note |
|---|---|---|---|
| id | `case_enquiry_id` (numeric string) | `case_id` (`BCS-########`) | Different id formats |
| open_time | `open_dt` (Boston wall-clock, no zone, e.g. `2026-05-01 07:02:18.757`) | `open_date` (Boston wall-clock despite the `+00` suffix, e.g. `2026-07-16 16:10:24.446642+00`) | BOTH systems are America/New_York wall-clock; the `+00` is a mislabel (87,951 of 87,951 rows have it). Do NOT convert from UTC. See "Time zones" below |
| target_time | `sla_target_dt` | `target_close_date` | Legacy target null for some open cases |
| close_time | `closed_dt` | `close_date` | Both null while open; every `Closed` new row has `close_date` |
| on_time | `on_time` ONTIME/OVERDUE | `on_time` ONTIME/OVERDUE | Same values |
| status | `case_status` Open/Closed | `case_status` Closed / In progress / Create / Submit / Needs Reallocation | New system has more states; treat only `Closed` as closed |
| closure_text | `closure_reason` (templated, e.g. `Case Closed. Closed date : 2026-05-01 08:57:13.83 Resolved ...`) | `closure_reason` (4 coded values: Resolved, Noted, Transitioned, Resolved successfully) plus `closure_comments` (free text) | Legacy has one templated string; new splits a code and a comment. Normalized text = `closure_comments` else `closure_reason` |
| type_raw | `type` (197 distinct values) | `service_name` (103 distinct) | `case_topic` always equals `service_name` (verified, 0 differences) |
| category | `reason`, `subject`, `case_title`, `queue` | `case_topic`, `assigned_team` | New system drops `subject`/`reason`/`queue`/`case_title` |
| department | `department` (code, e.g. `GEN`, `BTDT`) | `assigned_department` (name, e.g. `Public Works Department (PWD)`) | Different vocabularies |
| source | `source` (Employee Generated 1.48M, Citizens Connect App, Constituent Call, City Worker App, Self Service, Twitter, Maximo Integration) | `report_source` (BOS311 57,910; Call 30,040; Email 1) | New system has NO city-originated values, so the planned-follow-up source test (zombie-definition.md step 6) has no direct new-system equivalent |
| lat / lon | `latitude`, `longitude` (99.39% non-null and non-zero; 100% in Boston bounds) | `latitude`, `longitude` (99.9% non-null for cases opened since 2025-10-01) | Same meaning; new system has fewer repeated points. Legacy top placeholder points, both dropped: 42.3603,-71.0583 (4,808 rows) and 42.3595,-71.0588 (1,610); 18,512 legacy rows have no coordinates |
| street/address | `location` (full address, double-spaced), `location_street_name`, `location_zipcode` | `full_address`, `street_number`, `street_name`, `zip_code` | New system gives the number separately |
| geography | `fire_district, pwd_district, city_council_district, police_district, neighborhood, neighborhood_services_district, ward, precinct` | `neighborhood, public_works_district, city_council_district, fire_district, police_dist(rict), ward, precinct` | `pwd_district`->`public_works_district`; neighborhood_services_district dropped |
| photos | `submitted_photo`, `closed_photo` | `submitted_photo`, `closed_photo` | Same |
| geometry | `geom_4326` | none | Legacy only |

Column-order note: the new file lists `longitude` BEFORE `latitude` (the legacy file lists latitude first). Never read by position; always read by column name.

## VERIFIED new-system data check (go/no-go: GO, see docs/DECISIONS.md)
Records opened on/after 2025-10-01 (n = 86,994): coordinates 99.90%, address 99.49%, `closure_reason` 85.67% (97.92% of closed), `closure_comments` 64.69% (73.91% of closed).

## Row counts by open year and system (snapshot 2026-11-12)
| Year | legacy | new system |
|---|---|---|
| 2015 | 202,066 | 0 |
| 2016 | 210,483 | 0 |
| 2017 | 245,475 | 0 |
| 2018 | 257,610 | 0 |
| 2019 | 253,782 | 0 |
| 2020 | 246,165 | 0 |
| 2021 | 269,665 | 0 |
| 2022 | 272,931 | 0 |
| 2023 | 307,791 | 0 |
| 2024 | 306,756 | 0 |
| 2025 | 276,093 | 4,129 |
| 2026 (to Nov 12) | 191,730 | 83,822 |

## Case status values
Legacy: Closed 2,725,534; Open 315,013. New: Closed 76,828; In progress 11,106; Create 9; Needs Reallocation 6; Submit 2.

## Related datasets (PDDL, updated nightly)
- Boston Street Segments (SAM system): segment matching.
- Live Street Address Management (SAM) Addresses: "Check my street" search (build a compact client-side index).

## Expected fields (legacy format) (SUPERSEDED)
SUPERSEDED: this was the pre-kickoff guess; use the verified inventory in the Source and field mapping sections above.
`case_enquiry_id, open_dt, target_dt, closed_dt, ontime, case_status, closure_reason, case_title, subject, reason, type, queue, department, submitted_photo, closed_photo, location, fire_district, pwd_district, city_council_district, police_district, neighborhood, neighborhood_services_district, ward, precinct, location_street_name, location_zipcode, latitude, longitude, source`

## Normalized schema (what the pipeline produces)
`id, open_time_utc, open_time_local, target_time, close_time_utc, close_time_local, on_time (bool|null), status, closure_text, type_raw, type_family, queue, department, neighborhood, district, lat, lon, street, source, system ('legacy'|'new')`

## Type families (first draft; machine-readable copy in `pipeline/undead311/ingest/type_families.csv`)
Columns: `system, type_raw, type_family, scope_tier, city_originated_type`. `scope_tier` is `core` (in scope: persistent physical defects), `sensitivity` (outside the headline, reported as a sensitivity check; the only such type is new-system Traffic Signal Request) or `excluded` (kept in the file for audit only: event-type families graffiti, missed_trash, abandoned_vehicle, street_litter, plus Catchbasin, Traffic Signal Inspection, Pavement Marking Inspection, General Lighting Request). The `secondary` tier no longer exists. `city_originated_type` is true for Pothole Repair (Internal), Sidewalk Repair (Internal) and StreetLight Pole WO (step 6 of zombie-definition.md). Every type not listed is out of scope. Rows in scope after narrowing (valid coordinates): legacy 374,730; new 13,116 (13,157 before coordinate cleaning). Decision: new-system Traffic Signal Request (475 rows, all with valid coordinates) is sensitivity-only because it has 0 links and 11 of 50 sampled closure comments describe a physical defect; Street Light Other (1,081) stays in the headline because it is the successor of five in-scope legacy defect types (176 links), flagged as a migration catch-all; see docs/DECISIONS.md. Twelve successor types that were not listed before are now explicit `excluded` rows.
Families below are marked **core**, **sensitivity** or **excluded**.
| type_family | legacy `type` values | new-system `service_name` values |
|---|---|---|
| pothole_roadway | Request for Pothole Repair (133,981), Pothole Repair (Internal), Roadway Repair, BWSC Pothole, Highway Maintenance | Pothole (2,553) |
| sidewalk | Sidewalk Repair (Make Safe) (62,053), Sidewalk Repair, Sidewalk Repair (Internal) | Sidewalk Repair (3,096) |
| streetlight | Street Light Outages (57,809), ~~General Lighting Request~~ (excluded), Street Light Knock Downs, Knockdown Replacement, StreetLight Pole WO, Street Light Longterm Repair | Street Light Outage (4,849), Street Light Other (catch-all for migrated cases), Street Light Knockdown, Street Light Electrical Safety |
| traffic_signal | ~~Traffic Signal Inspection~~ (56,145; excluded), Traffic Signal Repair | Traffic Signal Request (sensitivity only), Traffic Signal Knockdown |
| sign | Sign Repair (70,855), Missing Sign | Missing / Knocked Down Sign, Damaged/Faded Sign, Knocked Down Sign |
| pavement_marking | Pavement Marking Maintenance, ~~Pavement Marking Inspection~~ (excluded) | Crosswalk Maintenance, Road Marking Maintenance, Lane Divider |
| street_fixture | ~~Catchbasin~~ (excluded), Sidewalk Cover / Manhole, Utility Casting Repair | Utility Casting Repair, Missing Manhole Cover, Fences/Guardrails/Bollards |
| graffiti (excluded) | Graffiti Removal (38,952), PWD Graffiti | Illegal Graffiti (1,371) |
| missed_trash (excluded) | Missed Trash/Recycling/Yard Waste/Bulk Item (143,566) | Missed Waste Pick-up (4,611) |
| abandoned_vehicle (excluded) | Abandoned Vehicles (55,215) | Abandoned Vehicles (450) |
| street_litter (excluded) | Requests for Street Cleaning (216,017), Empty Litter Basket, Illegal Dumping, Litter Basket Maintenance | Litter & Debris (11,546), Illegal Dumping or Disposal, Overflowing Trash, Broken Public Waste Receptacle |

Not covered by the draft: new-system types that have no legacy twin (e.g. Domestic Animal Issue, Wild Animal Issue, Pruning Request, Park Groundskeeping) are out of scope.

### Transfer/migration closures and mirrors
`TRANSFER_CLOSURE_RE` (`pipeline/undead311/ingest/closure_flags.py`, case-insensitive): `BCS-?\d+|resubmitted as|see new case|new case (has been created|number|entered|ref|#)|a new case has been created|transferr?ed|migrat|transition(ed)? to`. Boilerplate "please submit a new case" / "open a new case" is deliberately NOT matched (resident advice, not a transfer).
- All legacy rows, any type: 7,538 match (by close year: 2015 33; 2016 901; 2017 787; 2018 1,436; 2019 1,033; 2020 317; 2021 181; 2022 125; 2023 403; 2024 356; 2025 409; 2026 1,553; no close date 4). Literal "transferred"/"migrated": 97.
- In-scope legacy: 707 match (335 contain a BCS-id; 131 "Resubmitted as ..."; 225 "new case #/ref/created/number/entered"; 16 literal transferred/migrated/transition-to); 341 closed on/after 2025-08-01.
- Of the 335 in-scope legacy cases with a BCS-id, 263 point to a case that exists in the new file; 193 of those successors are in scope, but only 3 are the same type_family (190 were re-filed under a different service). Successor open minus legacy close: median -0.05 h; successor location median 1.1 m from the original. Transfers are mostly cross-family, so the rule matters for the 3 same-family ones and for text-only transfers.
- New-system closure codes map to Coroner labels: Resolved and Resolved successfully to resolved, Noted to noted, Transitioned to referred. A Transitioned closure (a transfer) is never an original; Noted closures stay originals (closed without a repair). In-scope new closures (after the Traffic Signal Request change): Transitioned 746, Noted 820.
- Not matched, reported only: 4,190 in-scope legacy closures "Referred to External Agency" / reallocated / sent to PWD (a hand-off to another agency, not a copy).
- Mirrors: cross-system, same family, within 30 m, open times within W hours: W=3: 1 pair; W=6: 1 pair; W=12: 1 pair; W=24: 3 pairs. `MIRROR_WINDOW_HOURS = 6`.
- Sample check: of the 300 cross-system pairs in the kickoff sample, 212 fall out of scope (traffic_signal 83, missed_trash 63, abandoned_vehicle 39, graffiti 22, pavement_marking 5); of the 88 in scope, 4 have a transferred original and 0 are mirrors, leaving 83 survivors. The rebuilt sample (15,221 rows, 5.11 MB, with `closure_code` for new-system rows) has 274 candidate pairs: 265 survive, 9 transferred originals, 0 mirrors.

### Type crosswalk from the 263 linked pairs
Successor types in the new system for the 263 in-scope legacy cases whose closure text names a BCS-id that exists in the new file (by legacy in-scope type):

| Legacy in-scope type | Linked | Successors in the new system |
|---|---|---|
| Request for Pothole Repair | 116 | Street Light Other 108, Pothole 3, Parks General Request 3, Tree or Stump Removal 1, Park Groundskeeping 1 |
| Sidewalk Repair (Make Safe) | 71 | Street Light Other 27, Pruning Request 15, Park Groundskeeping 11, Tree or Stump Removal 6, Park Suggestions 3, Planting Request 3, Fallen Tree or Branches 2, Parks General Request 2, Broken Park Equipment 2 |
| Sign Repair | 43 | Street Light Other 11, Street Light Knockdown 9, Utility Contractor Complaints 6, Park Groundskeeping 3, Parks General Request 3, Street Light Outage 2, Pruning Request 2, and 1 each Illegal Graffiti, Pothole, Fences/Guardrails/Bollards, Illegally Blocked Sidewalk, Broken Park Equipment, Litter & Debris, Unauthorized Signage |
| Traffic Signal Repair | 32 | Street Light Other 29, Street Light Knockdown 1, Park Graffiti 1, Illegal Graffiti 1 |
| Sidewalk Cover / Manhole | 1 | Street Light Other 1 |

Street Light Other is the migration catch-all: 176 of 263 links (67%). Traffic Signal Request has 0 links. By tier: 193 successors in core types, 3 in excluded types, 67 in types not in `type_families.csv` (12 distinct types, now listed explicitly as excluded rows). No existing mapping is contradicted by the links.

## New-system closure codes and top 30 closure_comments for in-scope types
In-scope (narrowed, before the Traffic Signal Request change) new-system rows, n = 13,632. The 4 `closure_reason` codes: Resolved 5,642 (plus 39 not closed); Noted 880; Transitioned 772; Resolved successfully 678; null 5,660 (4,660 In progress; 1,000 Closed with no code). Closed in-scope rows: 8,904, of which 5,141 have no `closure_comments`; 2,335 distinct comments.
Top 30 `closure_comments` (lower-cased): completed by task (466) · violation issued. (199) · reallocated to non-city of boston stakeholder (199) · duplicate request (106) · request completed (90) · violation issued. - we have notified bwsc, and they are scheduling repairs. (77) · no issue found at location (65) · roadway has been repaired. (59) · request resolved (43) · duplicate case (41) · duplicate case - this report is a duplicate of another open case. case has been closed. (33) · unable to locate (28) · sidewalk has been repaired (27) · completed by task - replace photo cell light on (26) · light is on no trouble found (25) · private property (25) · completed by task - replace photo cell light is on (24) · area maintained by private owner - property owners responsibility. (24) · respliced wires in pull box (24) · see notes, area has been inspected (24) · light is on (24) · no trouble found light is on (22) · completed by task - installed new 40watt fixture and photo cell light is on (22) · we have notified bwsc, and they are scheduling repairs. (20) · pothole has been filled. (20) · potholes repaired (19) · pothole has been filled. - potholes repaired (17) · we have notified the utility responsible, and they are scheduling repairs. (17) · see notes, area has been inspected - engineer has been notified of your concern (17) · violation issued. - we have notified national grid, and they are scheduling repairs. (16)
Code x comment pairs: Resolved/"completed by task" 466; Resolved/"violation issued." 199; Transitioned/"reallocated to non-city of boston stakeholder" 199; Noted/"duplicate request" 105; Noted/"no issue found at location" 65; Noted/"duplicate case" 41; Noted/"unable to locate" 28; Transitioned/"area maintained by private owner..." 24; Resolved successfully/"we have notified bwsc, and they are scheduling repairs." 20. Keyword counts: "schedul" 287, "inspect" 314, "duplicate" 322, "reallocat" 234, "temporar" 11, "safe" 79, "work order|wo " 78, "crew" 23.
Origin fields: in-scope `report_source` is BOS311 9,170 and Call 4,462 (no staff channel); `assigned_department` PWD 12,223, BTD 1,279, Parks & Recreation 85, null 45; `assigned_team` has 24 values (e.g. PWD Highway (BEAM) 5,337; PWD Street Lighting 4,184) and is not an origin field; none of the 17 in-scope service names contains "Internal" or "WO"; only 0.1 to 0.8% of in-scope new rows close within 5 minutes (legacy City Worker App: 29.2%), so fast closure is not an origin signal. Conclusion: the new system cannot show whether a case was staff-entered, hence `source_unknown` in zombie-definition.md step 6. For contrast, 44.5% of in-scope legacy cases opened since 2025-10-01 (n = 23,087) are city-originated by `source`.

## Closure text
Messy, partly templated. Deduplicate templates before labeling. Known pattern to detect: bulk backlog closures (identical text on many cases on the same day); 7,393 legacy cases mention "backlog" or "closing out".

### 30 most common legacy `closure_reason` templates (timestamps and numbers masked; legacy rows only, all years)
Prefix `Case Closed. Closed date : <timestamp>` is stripped. Variants with different case or date formats (`Day Mon dd hh:mm:ss EST yyyy`) are listed separately by the query, so some entries merge two spellings.
1. Bulk Item Automation (135,557)
2. Case Resolved (104,527 + 14,155 without a date prefix)
3. Resolved (93,581; later-format `Closed date : <Day Mon dd ...>` prefix)
4. Case Noted. Thank you for reporting ... Boston Transportation actively patrols city streets ... (37,105)
5. Case Noted (36,919)
6. Mattress Pickup Automation / Mattress Scheduled Pickup Automation (31,766)
7. Noted (28,065)
8. Duplicate of Existing Case (24,260)
9. Case Resolved. Marked completed at case creation (23,932)
10. Case Resolved CLEAR (23,690)
11. Case Resolved clear (22,420)
12. Resolved Removed (21,561)
13. Case Resolved new cart <N> delv on <date> (19,917; plus 9,588 uppercase variant)
14. VIOCOR: Violation Corrected (18,287)
15. ADCLSD: Administratively Closed (17,859)
16. Case Resolved Area ticketed (16,614)
17. Case Resolved The tree was pruned by Northern Tree Service to the City of Boston tree pruning specifications. (16,554)
18. Case Invalid (15,824)
19. Case Resolved tagged (14,304; plus 9,902 uppercase TAGGED)
20. Case Resolved All clear (13,355)
21. Empty text after the date (":") (12,940)
22. Case Resolved vehicle not at location (10,270)
23. Case Resolved Area clear (9,641)
24. Case Resolved Thank you for contacting Boston 311. The vehicle is no longer at this location. (9,458)
25. Case Noted Snow has been removed. (9,026)
26. Resolved Ticket has been issued (8,557)
27. Resolved All set (7,836)
28. NOVIO: No Violation Found/No Cause (7,946)
29. ROA: Refer to Other Agency/Division (7,637)
30. Case Resolved Thank you for contacting Boston 311. A citation has been issued. (7,613)

Also notable for the Coroner (rank 31+): "Case Resolved This location has been inspected and where possible temporary repairs or safety measures ..." (6,783; candidate `made_safe_temporary`); "Case Invalid This case has been closed as there is not enough information ..." (6,637); "Internal Case Performed by Highway Maintenance crew." (7,079); "Duplicate of Existing Case <N>" (5,101).

### 30 most common new-system `closure_comments` (lower-cased; 35,000+ nulls, closure_reason always available as the code)
citation issued. (4,044) · request completed (1,674) · no violation found by code enforcement (1,673) · officer dispatched (1,672) · animal has been collected (1,269) · item has been picked up (1,174) · needles have been picked up. (1,107) · reallocated to non-city of boston stakeholder (1,042) · vehicle ticketed (999) · completed by task (892) · area has been swept (887) · case noted (817) · area has been treated (748) · item(s) removed (641) · debris has been picked up (616) · no violation found (543) · no vehicle found (523) · vehicle moved (485) · request completed - all set (436) · citation issued. - violation has been issued (420) · violation issued. (409) · trash collected (379) · no issue found at location (329) · private property (305) · duplicate request (285) · trash can has been emptied (280) · citation issued. - property has been cited (266) · yard waste collected (243) · completed by task - the tree was pruned by northern tree service ... (216) · unable to locate (199)
New-system `closure_reason` codes (closed rows): Resolved 55,999; Noted 14,193; Transitioned 3,117; Resolved successfully 1,938; null 1,581.

## Data quality rules
- Drop or flag coordinates outside Boston bounds. Detect placeholder coordinates automatically (points shared by an unusually high number of unrelated cases; real top placeholder points: 42.3603, -71.0583 (4,808 rows) and 42.3595, -71.0588 (1,610), both dropped; 42.3594, -71.0587 has 0 rows in either system and is not a placeholder).
- Times in both systems are America/New_York wall-clock (the new system's `+00` is a mislabel); store UTC + local via `times.py`.
- Scrub personal info (names, phone numbers, emails) from any free text before export.
