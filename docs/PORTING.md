# Porting The Undead 311 to another city

This page lists which parts of the repository are Boston-specific, which are generic, and what a new city has to supply. The last section maps New York City's 311 schema onto ours, using only NYC's published dataset documentation. No NYC code has been written or run. The effort figures are estimates for one engineer who knows this repository, not measurements.

## What the method needs from a city

1. A table of 311 cases with an id, an open time, a close time, a case type, a point, and some closure text.
2. A way to say which case types are persistent physical defects (see [zombie-definition.md](../.kiro/steering/zombie-definition.md) for the scope rule).
3. A street-segment file, so that two reports on one block can match without a radius guess. Optional: without it, every case is unsnapped and matching falls back to `RADIUS_M`.
4. A neighborhood polygon file, for the neighborhood views. Optional.
5. A table that maps the city's closure text to Coroner labels.

## Inventory

### Generic: reuse as is

| Piece | Where | Note |
|---|---|---|
| Incident clustering, candidate pairs, attribution, chains | `pipeline/undead311/detect/` (`core.py`, `edges.py`, `grid.py`, `match.py`, `model.py`) | Works on the normalized case table. Parameters in `params.py` are tested against the steering file. |
| Bulk-closure flag, confidence score | `detect/bulk.py`, `detect/confidence.py` | |
| Same-spot baseline, placebo, shift test, survival, shrinkage, funnels, trends, rates and intervals | `pipeline/undead311/stats/` | Needs only the detector output and the case table. |
| Export, schemas, contract tests | `pipeline/undead311/export/writers.py`, `schemas/` | `export/privacy.py` is partly Boston-specific, see below. |
| DuckDB access, path fallback, snapshot and judging tools | `duck.py`, `paths.py`, `snapshot.py`, `pipeline/scripts/` | |
| Web app logic and pages | `web/src/` | Components, charts, filters, table view, tour, share images. |
| CI, budgets, property tests | `.github/workflows/`, `pipeline/tests/property/` | |

### Boston-specific: replace

| Piece | Where | What is Boston about it |
|---|---|---|
| Two-system loader and normalizer | `ingest/load.py`, `ingest/normalize.py` | Reads the legacy yearly files and the 2025 new-system file by column name. A city with one schema needs one mapping. |
| Time handling | `ingest/times.py` | Both Boston systems publish America/New_York wall-clock times, and the new system's `+00` suffix is a mislabel. Another city needs its own check. |
| Migration and mirror rules | `ingest/closure_flags.py`, zombie-definition step 9 | `BCS-` ids, "Resubmitted as" text, `MIRROR_WINDOW_HOURS`, the Transitioned code. They exist only because Boston changed systems in 2025. |
| Case-type crosswalk | `ingest/type_families.csv` (74 rows) | Boston `type` and `service_name` values mapped to seven families, with scope tier, city-originated flag and the Street Light Other catch-all. |
| City-originated test | `detect/core.py` (`CITY_SOURCES`), `type_families.csv` | Names Boston's legacy `source` values and internal case types. |
| Department crosswalk | `ingest/department_crosswalk.csv`, `ingest/departments.py` | Boston department codes and names. |
| Neighborhood folding | `ingest/neighborhoods.py` | `ALIASES` folds the City's 26 polygon names into 17 legacy names. |
| Street segments | `ingest/snap.py`, `ingest/geometry.py`, `export/privacy.py` | The logic is generic. The field names are SAM's: `F_ZLEV` and `T_ZLEV` for z-levels, and a guessed list of class keys for residential streets (`CLASS_KEYS`; the real SAM field was never confirmed). |
| Cleaning constants | `ingest/clean.py` | Boston bounding box, two placeholder points, the `Test` department. |
| Closure-text labels | `data/labels/coroner_labels.csv` (3,915 templates), `coroner/phrases.py` | Boston's templated closure strings and leading phrases. |
| Personal-data scrub | `ingest/pii.py`, `first_names.py`, `staff_names.py` | Built from Boston closure notes, where staff names appear. |
| Web copy, map and street search | `web/src/copy/en.json`, `web/src/map/style.ts` (`BOSTON_CENTER`), `web/public/tiles/boston.pmtiles`, `web/scripts/make-street-index.ts` | Names, credits, the basemap extract, and the SAM-based address index. |
| Answer key | `pipeline/tests/fixtures/` | The test town is synthetic, but scenarios such as the mirror copy and the Transitioned closure are Boston's. |

Two generic pieces carry hidden Boston assumptions. The detector tags origin only for `system == "legacy"`, so a one-system city needs that branch rewritten. The statistics treat the new-system `source_unknown` tier as a second population.

## What a new city must supply

| Item | Effort | Notes |
|---|---|---|
| Loader and normalizer for the city's file | 1 to 2 days | Map columns, parse times, keep every column as text on load as `load.py` does. |
| Time zone check | 0.5 day | Compare the hour-of-day histogram of open times with business hours, as `data-dictionary.md` does for Boston. |
| Scope decision and type crosswalk | 2 to 4 days | The owner decides what counts as a persistent physical defect. This is a judgement, not code, and must be logged before any count is run. |
| Segment adapter | 1 to 2 days | Read the city's centerline file, set the snap distance, decide whether z-levels exist. Without a file, skip it and use radius matching. |
| Neighborhood polygons and aliases | 1 day | |
| Closure-text labels | 2 to 5 days | Depends on whether the city's text is templated. A small table plus the leading-phrase rules can cover it. A hand-labeled random 200 measures accuracy (`make coroner-eval`). |
| City-originated rule | 0.5 to 3 days | Zero if the data has a field that shows who opened a case. If it does not, every re-report after a made-safe, referred or planned-follow-up closure goes to the `source_unknown` tier. |
| Privacy review | 1 day | Street class for block-level display, the personal-data scrub, a check for repeated coordinates that are placeholders. |
| Copy, basemap extract and credits | 2 to 3 days | Human-written copy per [voice.md](../.kiro/steering/voice.md); the basemap extract must be self-hosted. |
| Full-data run, baseline and placebo review | 2 to 4 days | Expect the placebo to need attention. Boston's did not pass. See the Limits section of the [README](../README.md). |
| Validation | 3 to 5 days | A seeded sample of possible zombies checked against the city's own closure records, with rules fixed before reading. |

Total: about 3 to 5 weeks of one person's time, dominated by the scope decision, labels and validation. These are estimates.

## Worked example: New York City

Source: the [311 Service Requests from 2020 to Present](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9) page on NYC Open Data. Its column list and descriptions were read on 2026-11-23 from the dataset's metadata, and value counts come from queries to the same dataset on that date, so they will drift. The 2010 to 2019 requests are a separate dataset, [311 Service Requests from 2010 to 2019](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-2019/76ig-c548); a 2015 start like Boston's needs both. The dataset page states that the data covers only requests that can be directed to specific agencies. License terms are on the dataset page; read them before redistributing.

### Column mapping

| Normalized field | NYC column | Notes |
|---|---|---|
| `id` | `unique_key` | One schema, so no `system` split. Set `system` to a constant. |
| `open_time` | `created_date` | Floating timestamp with no zone in the sample row (`2024-10-29T09:26:00.000`). The documentation read does not name a zone. Run the hour-of-day check before assuming America/New_York. |
| `close_time` | `closed_date` | Null while open. |
| `status` | `status` | Values seen: Closed, In Progress, Open, Pending, Assigned, Started, Unspecified, Cancel. Treat only Closed as closed. |
| `on_time` | none | The column list has `due_date`, described as when the agency is expected to update the request. `closed_date <= due_date` is a stand-in, and it is a different SLA concept than Boston's `ONTIME` flag. Say so on the scorecard. |
| `closure_text` | `resolution_description` | Describes the last action taken. May describe next steps. |
| `closure_code` | none | No code column. The label table has to carry the whole job. |
| `type_raw` | `complaint_type` plus `descriptor` | Two levels, with `descriptor_2` as a third. Boston's table is keyed by one string, so key ours as `complaint_type / descriptor`. |
| `department` | `agency` (acronym), `agency_name` | One vocabulary, so no department crosswalk. |
| `neighborhood` | `community_board` (provided by geovalidation), `borough` | NYC has no neighborhood column in the file. Use community boards, or join polygons from another NYC dataset. |
| `district` | `council_district`, `police_precinct` | |
| `lat`, `lon` | `latitude`, `longitude` | Also `x_coordinate_state_plane`, `y_coordinate_state_plane`. Roughly a quarter of Street Condition requests had no latitude when queried (130,773 of 528,941), against under 1% of Boston's in-scope cases. A case with no point cannot snap to a segment, so more NYC cases than Boston's would match by radius. |
| `street` | `incident_address`, `street_name`, `cross_street_1`, `cross_street_2`, `intersection_street_1`, `intersection_street_2` | `address_type` says which kind of location the request has (values seen: ADDRESS, INTERSECTION, BLOCKFACE, and others). Whether a point for an intersection or block face sits at the exact problem is not stated in the documentation. Test how often one coordinate repeats before choosing `RADIUS_M`. |
| `source` | `open_data_channel_type` | Values seen: ONLINE, PHONE, MOBILE, UNKNOWN, OTHER. This is how a request arrived, not who opened it, and the documentation names no staff-entered value. Treat origin as unknown, as for Boston's new system. |

NYC has other columns Boston lacks (`bbl`, `landmark`, `facility_type`, taxi and bridge fields). Ignore them.

### Scope and type crosswalk (a proposal for the owner to decide)

Complaint types for the Department of Transportation (`agency = DOT`), with counts at query time, suggest this mapping to our families:

| Family | NYC `complaint_type` | Count seen |
|---|---|---|
| pothole_roadway | Street Condition (descriptors Pothole 311,419; Cave-in 68,359; Failed Street Repair 26,569; Rough, Pitted or Cracked Roads 21,072), Highway Condition | 528,752; 25,198 |
| sidewalk | Sidewalk Condition, Curb Condition (judgement call) | 171,134; 46,990 |
| streetlight | Street Light Condition | 314,535 |
| traffic_signal | Traffic Signal Condition | 291,047 |
| sign | Street Sign - Damaged, Street Sign - Missing, Street Sign - Dangling, Highway Sign - Damaged, Highway Sign - Missing | 34,831; 27,109; 24,958; 785; 366 |
| pavement_marking | Street Condition with descriptors Line/Marking - Faded (5,508) and Line/Marking - After Repaving (3,888) | |
| street_fixture | Street Condition with descriptors such as Plate Condition - Noisy (17,344) and Plate Condition - Shifted (3,826); Defective Hardware (35,022) needs its meaning confirmed | |

Out of scope by the Boston rule: Illegal Parking, Noise types, Blocked Driveway, Missed Collection, Graffiti, Encampment and Homeless Person Assistance (about people), the housing-condition types, and Broken Parking Meter. A few agency-level questions stay open: `DEP Street Condition` (655 rows) sits under another agency, and Bridge Condition and Bike Rack Condition need a decision. Log each decision with a date before any count, as zombie-definition.md does.

Because descriptors drive the family, one `Street Condition` case can land in three families. The crosswalk must key on `complaint_type` plus `descriptor`, and the table should list unlisted descriptors as `unlisted_type` exclusions, which the cleaner already counts.

### Closure text

For Street Condition potholes, `resolution_description` is templated agency text. The most common values, in our words with counts at query time:

| Count | Meaning | Coroner label |
|---|---|---|
| 207,516 | The department inspected and repaired the problem | resolved |
| 51,354 | A duplicate of an earlier complaint, which is being addressed | duplicate |
| 28,491 | Inspected, did not find the reported problem | noted |
| 6,859 | Inspected and found the problem was fixed | noted (the city did not make this repair) |
| 5,487 | Referred to the Inspections Unit | referred |
| 4,571 | Referred to the maintenance unit for repair | referred |
| 4,985 | Status not available online | other |

The top seven templates cover about 309,000 of the 311,000 pothole requests, so the first label table is small. Other agencies' types will need their own look. Zombie-definition step 6 depends on `made_safe_temporary`, `referred` and `planned_followup`, so check that the templates contain those cases before trusting the planned-follow-up filter. In the pothole templates above only the referral ones fit.

### Street segments

The city publishes a [Centerline (CSCL)](https://data.cityofnewyork.us/City-Government/Centerline/inkn-q76z) dataset, described as a road-bed representation of streets with address ranges, traffic directions, road types and segment types; its [metadata](https://github.com/CityOfNewYork/nyc-geo-metadata/blob/main/Metadata/Metadata_StreetCenterline.md) is on GitHub. To use it, write a loader like `load_segments` in `ingest/snap.py`. Open questions, none answered in the pages read: whether it carries z-levels like SAM's `F_ZLEV` and `T_ZLEV`, whether it carries node ids (if it does, use them instead of deriving intersections from segment endpoints), and which field marks residential streets for the block-level privacy rule.

### What would change in the detector

- No migration. Disable the mirror and transfer rules for NYC (step 9 of zombie-definition.md). They are pre-registered, so the change goes in the change log with its reason.
- Every re-report has an unknown origin. After a `made_safe_temporary`, `referred` or `planned_followup` closure it would go to `source_unknown`, and after any other closure it stays in the headline. City crews cannot be separated out, so the `city_rereport` tier would be empty, and the headline could include crew-opened re-reports that Boston's would exclude.
- With a quarter of cases lacking a point, more matches use the radius than in Boston, so run the sensitivity grid (`RADIUS_M` 15, 30, 50) before reading any count.

### Chicago

Chicago was not mapped. A second mapping would repeat the same steps: read the column list, find the closure field, find the origin field, and check coordinates, times and street segments.
