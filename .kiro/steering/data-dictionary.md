---
inclusion: auto
name: data-dictionary
description: Boston 311 dataset fields, case-type families, closure-reason patterns. Use when writing ingest, detection, or any code that reads 311 data.
---
# Boston 311 data dictionary

**Status: VERIFIED against the Nov 12, 2026 snapshot (kickoff session; see `data/SNAPSHOT.md`).** Counts below come from DuckDB tables `raw_legacy` and `raw_new`. Re-verify when the schema changes.

## Source
Analyze Boston dataset "311 Service Requests" (yearly CSV resources, updated daily). License: Open Data Commons PDDL. Use the dataset's **CRM Value Codex** PDF to interpret codes.

## Verified file inventory (snapshot 2026-11-12)
- Legacy yearly CSVs 2015-2026 (2011-2014 exist but are not downloaded): 3,040,547 rows, 29 columns plus `geom_4326`, all with `case_enquiry_id` unique within a year. The 2026 file is still growing, so legacy cases continue after Oct 2025.
- One NEW SYSTEM CSV: 87,951 rows opened 2025-08-01 to 2026-11-11 (`case_id` like `BCS-00256693`). There is no separate Jan-Oct 2025 legacy file; 2025 is one legacy file.
- No id overlap between systems (legacy ids are numeric `1010...`). The two systems overlap in time (Aug 2025 on), so cross-system matching is by location/time/type only.

## The October 2025 system change
The 311 system changed in October 2025 and **field names differ** (e.g., `open_dt` → `open_date`). Expect three resource groups: yearly legacy files (through 2024), a Jan–Oct 2025 legacy file, and a new-system file (Oct 2025 onward). The ingest layer maps both to the normalized schema and records `system`.

## Source channel (`source`)
Known legacy values: Constituent Call, Citizens Connect App, City Worker App, Self Service, Employee Generated, Twitter, Maximo Integration. City-originated values (Employee Generated, City Worker App, Maximo Integration) matter for planned follow-ups (see zombie-definition.md).

## VERIFIED legacy vs. new system field comparison
| Normalized | Legacy column | New-system column | Difference / verified note |
|---|---|---|---|
| id | `case_enquiry_id` (numeric string) | `case_id` (`BCS-########`) | Different id formats |
| open_time | `open_dt` (local time, no zone, e.g. `2026-05-01 07:02:18.757`) | `open_date` (UTC, e.g. `2026-07-16 16:10:24.446642+00`) | Convert new system to America/New_York |
| target_time | `sla_target_dt` | `target_close_date` | Legacy target null for some open cases |
| close_time | `closed_dt` | `close_date` | Both null while open; every `Closed` new row has `close_date` |
| on_time | `on_time` ONTIME/OVERDUE | `on_time` ONTIME/OVERDUE | Same values |
| status | `case_status` Open/Closed | `case_status` Closed / In progress / Create / Submit / Needs Reallocation | New system has more states; treat only `Closed` as closed |
| closure_text | `closure_reason` (templated, e.g. `Case Closed. Closed date : 2026-05-01 08:57:13.83 Resolved ...`) | `closure_reason` (4 coded values: Resolved, Noted, Transitioned, Resolved successfully) plus `closure_comments` (free text) | Legacy has one templated string; new splits a code and a comment. Normalized text = `closure_comments` else `closure_reason` |
| type_raw | `type` (197 distinct values) | `service_name` (103 distinct) | `case_topic` always equals `service_name` (verified, 0 differences) |
| category | `reason`, `subject`, `case_title`, `queue` | `case_topic`, `assigned_team` | New system drops `subject`/`reason`/`queue`/`case_title` |
| department | `department` (code, e.g. `GEN`, `BTDT`) | `assigned_department` (name, e.g. `Public Works Department (PWD)`) | Different vocabularies |
| source | `source` (Employee Generated 1.48M, Citizens Connect App, Constituent Call, City Worker App, Self Service, Twitter, Maximo Integration) | `report_source` (BOS311 57,910; Call 30,040; Email 1) | New system has NO city-originated values, so the planned-follow-up source test (zombie-definition.md step 6) has no direct new-system equivalent |
| lat / lon | `latitude`, `longitude` (99.39% non-null and non-zero; 100% in Boston bounds) | `latitude`, `longitude` (99.9% non-null for cases opened since 2025-10-01) | Same meaning; new system has fewer repeated points. Legacy top placeholder points: 42.3603,-71.0583 (4,808 rows), 42.3595,-71.0588 (1,610); 18,512 legacy rows have no coordinates |
| street/address | `location` (full address, double-spaced), `location_street_name`, `location_zipcode` | `full_address`, `street_number`, `street_name`, `zip_code` | New system gives the number separately |
| geography | `fire_district, pwd_district, city_council_district, police_district, neighborhood, neighborhood_services_district, ward, precinct` | `neighborhood, public_works_district, city_council_district, fire_district, police_dist(rict), ward, precinct` | `pwd_district`->`public_works_district`; neighborhood_services_district dropped |
| photos | `submitted_photo`, `closed_photo` | `submitted_photo`, `closed_photo` | Same |
| geometry | `geom_4326` | none | Legacy only |

Column-order note: the new file lists `longitude` before `latitude`; always read by name.

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

## Expected fields (legacy format; verify)
`case_enquiry_id, open_dt, target_dt, closed_dt, ontime, case_status, closure_reason, case_title, subject, reason, type, queue, department, submitted_photo, closed_photo, location, fire_district, pwd_district, city_council_district, police_district, neighborhood, neighborhood_services_district, ward, precinct, location_street_name, location_zipcode, latitude, longitude, source`

## Normalized schema (what the pipeline produces)
`id, open_time, target_time, close_time, on_time (bool|null), status, closure_text, type_raw, type_family, queue, department, neighborhood, district, lat, lon, street, source, system ('legacy'|'new')`

## Type families (first draft; machine-readable copy in `pipeline/undead311/ingest/type_families.csv`)
Columns: `system, type_raw, type_family, scope_tier`. `scope_tier` is `core` (proposed in-scope) or `secondary` (optional). Every other type is out of scope (proposal only; the final list needs owner approval, see docs/DECISIONS.md).
| type_family | legacy `type` values | new-system `service_name` values |
|---|---|---|
| pothole_roadway | Request for Pothole Repair (133,981), Pothole Repair (Internal), Roadway Repair, BWSC Pothole, Highway Maintenance | Pothole (2,553) |
| sidewalk | Sidewalk Repair (Make Safe) (62,053), Sidewalk Repair, Sidewalk Repair (Internal) | Sidewalk Repair (3,096) |
| streetlight | Street Light Outages (57,809), General Lighting Request, Street Light Knock Downs, Knockdown Replacement, StreetLight Pole WO, Street Light Longterm Repair | Street Light Outage (4,849), Street Light Other, Street Light Knockdown, Street Light Electrical Safety |
| traffic_signal | Traffic Signal Inspection (56,145), Traffic Signal Repair | Traffic Signal Request, Traffic Signal Knockdown |
| sign | Sign Repair (70,855), Missing Sign | Missing / Knocked Down Sign, Damaged/Faded Sign, Knocked Down Sign |
| pavement_marking | Pavement Marking Maintenance, Pavement Marking Inspection | Crosswalk Maintenance, Road Marking Maintenance, Lane Divider |
| street_fixture | Catchbasin, Sidewalk Cover / Manhole, Utility Casting Repair | Utility Casting Repair, Missing Manhole Cover, Fences/Guardrails/Bollards |
| graffiti | Graffiti Removal (38,952), PWD Graffiti | Illegal Graffiti (1,371) |
| missed_trash | Missed Trash/Recycling/Yard Waste/Bulk Item (143,566) | Missed Waste Pick-up (4,611) |
| abandoned_vehicle | Abandoned Vehicles (55,215) | Abandoned Vehicles (450) |
| street_litter (secondary) | Requests for Street Cleaning (216,017), Empty Litter Basket, Illegal Dumping, Litter Basket Maintenance | Litter & Debris (11,546), Illegal Dumping or Disposal, Overflowing Trash, Broken Public Waste Receptacle |

Not covered by the draft: new-system types that have no legacy twin (e.g. Domestic Animal Issue, Wild Animal Issue, Pruning Request, Park Groundskeeping) are out of scope.

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
- Drop or flag coordinates outside Boston bounds. Detect placeholder coordinates automatically (points shared by an unusually high number of unrelated cases; known example: City Hall 42.3594, -71.0587).
- Times are local (America/New_York); store UTC + local.
- Scrub personal info (names, phone numbers, emails) from any free text before export.
