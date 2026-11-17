# Requirements: zombie-engine

## Introduction
The zombie engine turns Boston 311 records from both systems (legacy, and the new system from August 2025) into normalized cases, incidents and possible zombies, and exports schema-validated static files for the web app. It is the single implementation of `.kiro/steering/zombie-definition.md`: every rule and parameter comes from that file, and nothing here changes it. Requirements reference zombie-definition.md steps as "ZD step N".

Each requirement has an ID and a build layer (docs/PROJECT.md cut lines): **demo-critical** (by Tue Nov 17), **credibility** (by Sun Nov 22) or **delight**. Acceptance criteria use EARS form and are numbered `<ID>.<n>`.

Legacy ID: code written before these specs cites `REQ-ING-MIRROR`. It is covered by REQ-DET-2.2–2.4 and REQ-ING-CATCH, and the docstrings are updated in the tasks.

## Glossary
- **Case:** one 311 service request after normalization.
- **In-scope case:** a case whose resolved `scope_tier` is `core` or `sensitivity`.
- **Incident:** a group of closed in-scope cases that are true duplicates (ZD step 2). Incident ID = the smallest member case ID in string order.
- **Re-report (R):** a case that opens after an incident's close time (ZD step 3).
- **Possible zombie:** an incident with an attached resurrection that is not a planned follow-up (ZD step 5).
- **Tier:** `headline`, `source_unknown` or `sensitivity`. Only `headline` zombies are in the headline count.
- **Test town:** `pipeline/tests/fixtures/test_town.csv` (cases, drafted by Kiro) and `expected_zombies.json` (the answer, written by the owner).

---

### REQ-ING-1: Load raw data
**Layer:** demo-critical
**User story:** As the pipeline, I want both systems' raw CSVs in DuckDB, so every later step queries one database.
1. WHEN `make pipeline` runs, THE engine SHALL load every legacy yearly CSV (2015 onward) and the new-system CSV from `$DATA_DIR/raw/` into `$DATA_DIR/processed/undead311.duckdb`, recording row counts per file.
2. IF a raw file listed in `data/SNAPSHOT.md` is missing, THEN THE engine SHALL stop with a message that names the file and the command that downloads it (`make data-download`).
3. THE engine SHALL read raw files only through DuckDB, never row by row in Python.

### REQ-ING-PATH: Data location fallback
**Layer:** demo-critical
**User story:** As a developer in any environment, I want the data path to fix itself, so a different mount path never breaks a run.
1. WHEN `DATA_DIR` is unset, missing, or not writable, THE engine SHALL use `<repo root>/.local-data/data`, create it if needed, and log the path it chose.
2. THE engine SHALL resolve `<repo root>` at run time. In a git worktree, it SHALL use the main checkout's root (`git rev-parse --git-common-dir`), so worktrees share one data folder.
3. THE Makefile SHALL apply the same rule for every target that reads data.

### REQ-ING-NBR: Neighborhood naming
**Layer:** credibility
1. THE engine SHALL name each case's neighborhood by point in polygon against the City's neighborhood boundaries file for both systems, fold polygon names to one name set shared by both systems, and leave no case with a neighborhood name that is not an area (for example Boston). (Owner decision 2026-11-14, ops#96.)

### REQ-ING-2: Normalized schema
**Layer:** demo-critical
**User story:** As the detector, I want one schema for both systems, so matching never depends on the source format.
1. THE engine SHALL map legacy and new-system fields to the normalized schema in data-dictionary.md, plus `system`, `closure_code` (new system only), `scope_tier`, `city_originated_type`, `catch_all` and `predecessor_ids`.
2. WHEN a value can't be parsed (time, coordinate, status), THE engine SHALL set it to null and count the row under a named reason, never drop it silently.
3. THE engine SHALL produce identical normalized output for identical input, independent of input row order.

### REQ-ING-TZ: Time normalization
**Layer:** demo-critical
**User story:** As the detector, I want correct times across systems and daylight-saving changes, so "opened after closure" is true in real time.
1. THE engine SHALL treat both systems' timestamps as America/New_York wall-clock (ignoring the new system's `+00` suffix) and store `*_time_utc` and `*_time_local` using `pipeline/undead311/ingest/times.py`.
2. WHEN a wall-clock time falls in the fall-back hour, THE engine SHALL use the first occurrence and set `local_ambiguous`. WHEN it falls in the spring-forward gap, THE engine SHALL shift it forward and set `local_nonexistent`.
3. THE engine SHALL compare times only in UTC.

### REQ-ING-XWALK: Type crosswalk and scope
**Layer:** demo-critical
**User story:** As the detector, I want each case's family and tier from one table, so scope decisions live in one place.
1. THE engine SHALL take `type_family`, `scope_tier`, `city_originated_type` and `catch_all` from `pipeline/undead311/ingest/type_families.csv` by (`system`, `type_raw`).
2. WHEN a `type_raw` is not listed, THE engine SHALL treat the case as out of scope and count it under `unlisted_type`.
3. THE engine SHALL drop `excluded` cases from detection and display, and count them by family.

### REQ-ING-CATCH: Catch-all inheritance
**Layer:** demo-critical
**User story:** As the detector, I want Street Light Other cases to carry the family of the problem they continue, so a migrated pothole is matched as a pothole.
1. THE engine SHALL extract links from legacy closure texts with `extract_linked_case_id` (`closure_flags.py`), and record each linked legacy ID in the successor's `predecessor_ids`.
2. WHEN a new-system case has `catch_all = true`, THE engine SHALL set its family and tier with `resolve_catch_all`, using the predecessors' listed families.
3. IF the predecessors disagree, any predecessor type is unlisted, or there is no link, THEN THE engine SHALL keep the case's default family with tier `sensitivity`.
4. IF every predecessor has the same listed family and that family's tier is `excluded`, THEN the case SHALL inherit `excluded`, so it is out of scope and counted as `excluded_type` (as `resolve_catch_all` already does).
5. THE engine SHALL use the inherited family whenever the case is an original or a re-report in later matching.

### REQ-ING-CLEAN: Coordinates and placeholders
**Layer:** demo-critical
**User story:** As the detector, I want bad locations removed, so placeholder points don't create fake zombies.
1. THE engine SHALL drop cases with null coordinates, coordinates outside the Boston bounding box (latitude 42.2 to 42.45, longitude −71.2 to −70.9, the box the kickoff sample used in `pipeline/scripts/build_sample.py`; to be written into data-dictionary.md by the owner), or coordinates that round (4 decimals) to either placeholder point in ZD step 1.
2. THE cleaning step SHALL return the excluded case IDs by reason: `null_coords`, `out_of_bounds`, `placeholder`, `unlisted_type`, `excluded_type`.
3. THE engine SHALL report every exclusion by reason, family and system in `exclusions.json`.
4. THE engine SHALL also list candidate placeholder points (one coordinate shared by more than 200 unrelated cases) in a report, without dropping them, so the owner can add them to ZD step 1.

### REQ-ING-SNAP: Street-segment snapping
**Layer:** credibility
**User story:** As the detector, I want cases on Boston SAM street segments, so matches don't jump to parallel streets, and cases at one intersection still match.
1. THE engine SHALL snap every in-scope case to the nearest Boston Street Segments (SAM) line and store `segment_id` and `segment_snap_m`. A case is "snapped" only when `segment_snap_m <= 15`.
2. IF the segments file is missing, THEN THE engine SHALL leave every case unsnapped (radius matching only) and record `segments: missing` in `status.json` (the value `status.schema.json` allows; owner decision 2026-11-14, ops#75).
3. THE engine SHALL accept pre-snapped `segment_id` / `segment_snap_m` columns when present (the test town) and skip snapping for those rows.
4. WHEN the segments file is present, THE engine SHALL derive an `intersections` table from the segment geometry: an intersection is a segment endpoint (first or last vertex, matched at 6 decimal places of latitude and longitude and at the same z-level, `F_ZLEV` / `T_ZLEV`) shared by two or more segments. SAM has no node IDs, so endpoints are matched on coordinates. THE engine SHALL store, for each snapped case, the intersections within INTERSECTION_M of it (`near_node_ids`).
5. WHEN a case is pre-snapped without segment geometry (the test town), THE engine SHALL leave `near_node_ids` empty, so the intersection mode never applies to the fixture. Intersection matching is covered by unit and property tests that build their own small segment grids (REQ-DET-MATCH.2).
6. THE methods page SHALL state the known limitation: a shared endpoint is a segment break, and not every break is a cross street (a street can be split mid-block). The rule can therefore also join two cases on consecutive segments of one street that are both near such a break. Dead-end endpoints (about 15% of the distinct endpoints in the current SAM file) are not intersections.

### REQ-ING-PII: Personal-information scrubbing
**Layer:** demo-critical
**User story:** As a resident, I want my name and contact details kept off the site, so publishing case text never exposes me.
1. BEFORE any free text is exported, THE engine SHALL replace email addresses, phone numbers, names after honorifics or after "called by", "spoke with" and "per", and digit runs of 7 or more, with `[removed]`.
2. THE engine SHALL keep the case address and street name, which are public case locations.
3. THE engine SHALL count replacements per pattern in the run report, and never log the removed text.

### REQ-DET-PARAM: Parameters
**Layer:** demo-critical
**User story:** As the owner, I want parameters in one module that mirrors the steering, so the rules are changed only in zombie-definition.md.
1. THE engine SHALL define RADIUS_M = 30, WINDOW_DAYS = 60, INCIDENT_MAX_SPAN_DAYS = 7, MAX_SEGMENT_DIST = 75, SEGMENT_SNAP_M = 15, INTERSECTION_M = 15, BULK_MIN_CASES = 50, BULK_RATIO = 10 and MIRROR_WINDOW_HOURS = 6 in one module (`detect/params.py`; MIRROR_WINDOW_HOURS is imported from `closure_flags.py`).
2. THE engine SHALL accept parameter overrides only through an explicit argument (for the sensitivity grid), never through environment variables.
3. A unit test SHALL fail if any default differs from the value written in zombie-definition.md.

### REQ-DET-MATCH: Location matching
**Layer:** demo-critical
**User story:** As the detector, I want one location rule, so incidents and re-reports use the same notion of "same place".
1. WHEN both cases are snapped to the same `segment_id` and are at most MAX_SEGMENT_DIST apart, THE engine SHALL match them with `match_mode = segment`.
2. WHEN the two cases are not a segment match, are both snapped, and are on different segments, AND both are within INTERSECTION_M of the same intersection (REQ-ING-SNAP.4), THE engine SHALL match them with `match_mode = intersection`. The distance recorded is the sum of the two distances to that intersection.
3. OTHERWISE, THE engine SHALL match them only if at least one of them is unsnapped AND they are at most RADIUS_M apart (`match_mode = radius`). Two snapped cases that are not a segment or intersection match NEVER match: not on different segments (owner decision, zombie-definition.md change log 2026-11-13), and not on one segment more than MAX_SEGMENT_DIST apart.
4. THE engine SHALL compute distance with haversine, and find candidates through a grid bucket join, not an all-pairs join. The grid cell is large enough for the largest of RADIUS_M, MAX_SEGMENT_DIST and 2 × INTERSECTION_M.
5. WHEN the matching mode parameter is `radius`, THE engine SHALL ignore segments and intersections entirely and apply RADIUS_M to every pair (sensitivity grid). WHEN it is `segment`, requirements 1 to 3 apply and RADIUS_M only affects pairs with an unsnapped case.

### REQ-DET-1: Incidents
**Layer:** demo-critical
**User story:** As the detector, I want true duplicate reports grouped once, so one problem is counted once and a fast resurrection never disappears into its own original.
1. THE engine SHALL place every closed in-scope case in exactly one incident.
2. WHEN processing closed cases in (open time UTC, ID) order, THE engine SHALL add a case to an existing incident only if it matches a member's location (REQ-DET-MATCH), has the same family, opened strictly before the incident's earliest member close, and keeps the incident's span (first open to last close) within INCIDENT_MAX_SPAN_DAYS. Otherwise it SHALL start a new incident. WHEN several incidents qualify, it SHALL choose the smallest incident ID.
3. THE engine SHALL set the incident close time to its latest member close time, and the incident Coroner label to the label of that member (ties by member ID).
4. THE engine SHALL never make a case opened at or after an incident's earliest member close a member of that incident.

### REQ-DET-2: Candidate pairs
**Layer:** demo-critical
**User story:** As the detector, I want candidate pairs that obey time order exactly, so a re-report is always after the closure.
1. THE engine SHALL form a candidate pair (I, R) only if `R.open_time_utc > I.close_time_utc` (strictly), `R.open_time_utc <= I.close_time_utc + WINDOW_DAYS`, R has the same family as I, R matches the location of at least one member of I, and R is not a member of I.
2. THE engine SHALL exclude the pair if any member of I is a transferred original (`is_transferred_original`: a legacy transfer closure text, or new-system code Transitioned).
3. THE engine SHALL exclude the pair if R's `predecessor_ids` contains any member of I (a linked successor is never a re-report of its own predecessor).
4. THE engine SHALL treat R as a mirror copy, and attach it to NO incident, if R and any closed in-scope case of the same family at a matching location are in different systems and opened within MIRROR_WINDOW_HOURS of each other (`is_mirror_pair`). A mirror is one report, not a resurrection. Same-system pairs never use this rule.
5. THE engine SHALL count every excluded pair by reason (`transferred_original`, `linked_successor`, `mirror`) in the run report.

### REQ-DET-3: Attribution
**Layer:** demo-critical
**User story:** As the detector, I want each re-report counted once, so evidence isn't double-counted.
1. THE engine SHALL process cases R in (open time UTC, ID) order and attach each R to the eligible incident with the latest close time, ties by smallest incident ID.
2. THE engine SHALL attach each R to at most one incident.
3. THE engine SHALL set the incident's resurrection to its earliest attached R. `reports_after` is the number of attached Rs, and `gap_days` is (resurrection open − incident close) in days.

### REQ-DET-PF: Planned follow-ups, temporary fixes and unknown source
**Layer:** demo-critical
**User story:** As a reader, I want city follow-up work kept out of the zombie count and temporary fixes made visible, so the count is fair to the city.
In this requirement, R is the incident's resurrection (its earliest attached re-report, ZD step 5). Later attached re-reports count in `reports_after` but don't change the classification.

1. WHEN R is legacy and city-originated (`source` in Employee Generated, City Worker App or Maximo Integration, or `city_originated_type = true`), and the incident label is `made_safe_temporary`, `referred` or `planned_followup`, THE engine SHALL mark the incident `is_planned_followup` and SHALL NOT count it as a possible zombie.
2. WHEN R is a legacy resident report and the incident label is `made_safe_temporary`, THE engine SHALL count a possible zombie tagged `after_temporary_fix`.
3. WHEN R is a new-system case and the incident label is `made_safe_temporary`, `referred` or `planned_followup`, THE engine SHALL count a possible zombie tagged `source_unknown`.
4. WHEN the incident has any other label, THE engine SHALL NOT apply this requirement.

### REQ-DET-TIER: Headline and sensitivity tiers
**Layer:** demo-critical
**User story:** As a reader, I want the headline to include only cases the definition is sure about, with the rest available as a toggle, so nothing is silently added or dropped.
1. THE engine SHALL give every possible zombie exactly one tier. `sensitivity` applies if the incident or R has scope tier `sensitivity` (sensitivity-only types, and unlinked or ambiguous catch-all cases). Otherwise `source_unknown` applies if the zombie is tagged `source_unknown`. Otherwise the tier is `headline`.
2. THE engine SHALL compute the headline count from `headline` zombies only.
3. THE engine SHALL export counts for every tier, and the zombie records of every tier with the tier field, so the web app can offer the toggle.
4. THE engine SHALL never put an unlinked or ambiguous catch-all case in the headline, as an original or as a re-report.

### REQ-DET-CHAIN: Chains and repeat offenders
**Layer:** demo-critical (computation; the view is haunted-web, delight)
**User story:** As a reader, I want places that keep coming back counted, so repeat offenders stand out.
1. WHEN a possible zombie's resurrection R is closed, R's incident SHALL continue the chain. `chain_id` is the incident ID at the start of the chain. Planned follow-ups and separate deaths end a chain; their R's incident starts a new one.
2. THE engine SHALL set `times_risen` to the chain total: the number of possible zombies (all tiers) in the chain. Every zombie in the chain carries the same total.
3. THE engine SHALL mark a chain as a repeat offender when its count of headline-tier zombies is at least 3, and export both counts. The rule is the owner's decision (zombie-definition.md step 7).

### REQ-DET-SEP: A different kind of death
**Layer:** demo-critical
**User story:** As a reader, I want invalid and duplicate closures reported separately, so "closed as invalid" isn't confused with a failed repair.
1. WHEN an incident with label `invalid` or `duplicate` has an attached R, THE engine SHALL record it in `separate_deaths` and SHALL NOT count it as a possible zombie.

### REQ-DET-GOLD: Golden test town
**Layer:** demo-critical
**User story:** As the owner, I want the detector to reproduce my hand-written answer exactly, so the one-shot build has a correctness anchor.
1. THE golden test SHALL run crosswalk, catch-all inheritance, cleaning and detection on the raw fixture rows of `test_town.csv`, the same code path as full data. Only SAM snapping (pre-snapped columns) and the Coroner label join (`coroner_label` column) are skipped.
2. IF `expected_zombies.json` is missing, THEN THE golden test SHALL fail with "answer key missing: the owner writes it by hand" (never skip).
3. THE engine and its agents SHALL never write `expected_zombies.json`.
4. THE fixture loader SHALL ignore the `scenario` and `note` columns, and SHALL use the `coroner_label` column instead of the label join.
5. THE golden test SHALL compare, for each top-level key in `expected_zombies.json`, the engine's list sorted by `incident_id` (or `chain_id`), with every ID list inside a record sorted. Compared keys and fields:
   - `zombies`: incident_id, member_ids, resurrection_id, reports_after, match_mode, tier, after_temporary_fix, chain_id, times_risen.
   - `planned_followups`: incident_id, resurrection_id.
   - `separate_deaths`: incident_id, label, rereport_id.
   - `repeat_offenders`: chain_id, times_risen.
   - `excluded_ids`: `placeholder_or_invalid_coords` = null_coords + out_of_bounds + placeholder; `out_of_scope_type` = unlisted_type + excluded_type.
   - `incidents_with_several_members`: incident_id, member_ids.
   A key the owner leaves out of the file is not compared. An unknown key fails the test.

### REQ-ING-DEPT: Department crosswalk
**Layer:** credibility
**User story:** As a reader comparing departments, I want each department to be one row across both systems.
1. THE engine SHALL map every legacy department code and new-system department name to one key through `ingest/department_crosswalk.csv`, a data file whose every row names its source and a status (`official`, `mapped`, `flagged`).
2. A value with no mapping SHALL be kept under its own value, listed as flagged in the run report's anomalies with its in-scope count; a missing department stays empty.

### REQ-COR-1: Coroner templates and labels
**Layer:** demo-critical
**User story:** As the Coroner agent, I want a deduplicated list of closure-text templates, so labeling covers the most closures with the fewest calls.
1. THE engine SHALL mask timestamps, dates, numbers and case IDs in closure texts, deduplicate them into templates, and write `$DATA_DIR/processed/coroner_templates.csv` (template, n_cases, example_id), sorted by n_cases.
2. THE engine SHALL join `data/labels/coroner_labels.csv` by template. For new-system closures with code Transitioned, the label SHALL be `referred`. For other new-system closures, the template label SHALL be used when one exists, and otherwise `NEW_SYSTEM_CLOSURE_LABELS`.
3. WHEN a closed case has no label, THE engine SHALL use `other` and count it as `unlabeled`. The run report SHALL show the share of in-scope closed cases covered by labels.
4. THE engine SHALL reject any label outside the allowed set (resolved, noted, invalid, duplicate, referred, made_safe_temporary, planned_followup, bulk_backlog, other).

### REQ-COR-PHRASE: Leading-phrase labeler
**Layer:** credibility
**User story:** As a reader of the cause of death, I want closures with boilerplate openings and free text after them to be labeled, so the labels cover nearly every closed case.
1. THE engine SHALL label a closed case that the label table does not list by its leading phrase (`coroner/phrases.py`): deterministic rules in a fixed order (backlog wording, made-safe wording, scheduled wording, a hand-off to an agency, then the disposition word after the "Case Closed" boilerplate). A text no rule places stays `other` and counts as unlabeled.
2. THE precedence SHALL be: new-system Transitioned code, the label table, the new-system closure code, then the leading phrase. The run report SHALL count cases by label source (`labeled_by_table`, `_code`, `_phrase`).
3. `make coroner-eval` SHALL score the pipeline rule on `data/labels/coroner_random200.csv`, the Coroner's evaluation set (owner decision 2026-11-16: the planned 200 hand labels were never made), with a 20-row owner spot check drawn with a fixed seed in `docs/CORONER_SPOTCHECK.md`. The set is a seeded random draw of full-data closures labeled by the Coroner agent; the command writes the agreement with its Wilson interval to docs/VALIDATION.md. The target is at least 95% of in-scope closed cases labeled.

### REQ-COR-EVAL: Coroner accuracy
**Layer:** credibility
**User story:** As the owner, I want the Coroner's accuracy measured against my hand labels, so the cause of death shown on cards is trustworthy.
1. `make coroner-eval` SHALL compare `coroner_labels.csv` with the 200 hand labels in `data/labels/coroner_hand_labels.csv`, and write accuracy, a Wilson 95% interval and the top confusions to `docs/VALIDATION.md`.
2. IF the hand-label file is missing, THEN `make coroner-eval` SHALL say so and exit 0 (it is human input).

### REQ-BULK: Bulk-closure detector
**Layer:** credibility
**User story:** As a reader, I want mass "closed" days flagged, so backlog purges aren't mistaken for repairs.
1. THE engine SHALL flag a (department, close date, template) group as a bulk closure when it has at least BULK_MIN_CASES (50) cases and at least BULK_RATIO (10) times the department's usual daily count for that template, for the same department, day and template. The usual daily count is the median daily closure count of that department and template over the days that have closures. The parameters are in zombie-definition.md (step 10).
2. THE engine SHALL store the flag in a separate field, `bulk_closure`. It SHALL never overwrite the Coroner label, which ZD step 6 reads. THE engine SHALL export `bulk_closures.json` (groups with counts, department, date and template).

### REQ-CONF: Confidence score
**Layer:** demo-critical (formula and partial score); credibility (baseline and Skeptic terms)
**User story:** As a reader, I want a confidence score with a documented formula, so I can tell strong cases from weak ones.
1. THE engine SHALL compute `confidence` in [0, 1] from match quality, gap, type specificity, Coroner label (with the `bulk_closure` flag lowering it), `baseline_p` and surviving Skeptic objections, with the exact formula and weights written in `docs/METHODS.md` before the first full-data run.
2. WHEN `baseline_p` or Skeptic results aren't available yet, THE engine SHALL use the neutral value given in METHODS.md for that term and set `confidence_partial = true`.
3. THE web app SHALL never use the confidence score to choose judge-mode zombies or the validation sample (methods.md: raters are blind to it).

### REQ-SKEP: Skeptic objections
**Layer:** demo-critical (join); credibility (baseline evidence)
**User story:** As a reader, I want the strongest argument for coincidence on every card, so the evidence is honest.
1. THE engine SHALL write `$DATA_DIR/processed/skeptic_input.json` for the Skeptic agent. It SHALL cover the validation sample, every zombie in `judge_tour.json` (provisional or confirmed, REQ-STAT-TOUR) and the 200 headline zombies with the most re-reports. Selection never uses the confidence score.
2. THE engine SHALL join `data/labels/skeptic_objections.json` into `skeptic_notes` and `skeptic_verdict` by (incident ID, resurrection ID). Zombies without a review SHALL get `skeptic_verdict = not_reviewed`.

### REQ-SENS-RUN: Sensitivity runs
**Layer:** credibility
**User story:** As a reader, I want results for other reasonable definitions, so the definition isn't cherry-picked.
1. THE engine SHALL run the detector for every grid point (matching in {segment, radius} × RADIUS_M in {15, 30, 50} × WINDOW_DAYS in {30, 60, 90}) and store per-point counts by tier, family and department in the DuckDB table `grid_runs`.
2. THE engine SHALL make one extra run without Street Light Other (all tiers), as required by the zombie-definition.md change log.

### REQ-EXP-1: Exports and contracts
**Layer:** demo-critical
**User story:** As the web app, I want small, validated, deterministic files, so the site can't drift from the pipeline.
1. THE engine SHALL write `zombies`, `incidents` (summary), map points, autopsy cards, `exclusions`, `separate_deaths`, `repeat_offenders`, `bulk_closures` and `status` files to `web/public/data/`. `status.json` is written last and includes the stats status (`calibration_warning`, REQ-STAT-PLACEBO). `sensitivity_grid.json` is owned by durability-stats (REQ-STAT-GRID); the engine stores raw grid runs in the DuckDB table `grid_runs`. Each SHALL validate against its JSON Schema in `/schemas/` before it is written, or the run fails.
2. Every file SHALL carry `data_version` (snapshot date, short git SHA, parameter hash). Records SHALL be sorted by stable IDs (zombie ID = `<incident_id>:<resurrection_id>`).
3. Two runs on the same input SHALL produce byte-identical files.
4. THE engine SHALL write the DuckDB file atomically (build to a temporary file, then rename).

### REQ-EXP-SIZE: Payload budget
**Layer:** credibility
**User story:** As a phone user, I want the first view to load fast, so judge mode works on a phone.
1. THE engine SHALL keep the files needed for the first view (`status.json`, `points.json`, `stats/scorecard.json`, `stats/judge_tour.json`) under 3,000,000 bytes in total **measured as gzip transfer size** (what a phone downloads), AND no single first-view file SHALL exceed 8,000,000 bytes uncompressed (the browser parses it uncompressed). It SHALL shard cards by neighborhood and year and write plain JSON (no precompressed copies; the host compresses responses, owner decision ops#184).
2. THE engine SHALL report every exported file's raw and gzip size in the run report, and fail before writing anything if the first-view gzip budget or the 8 MB raw ceiling is exceeded. Gzip sizes use zlib level 6 with a zero timestamp, so a rerun reports the same number. (Changed in fix/fulldata-2: the budget was raw bytes; the full-data dry run full-1 measured `points.json` at 6.3 MB raw, which is about 1 MB gzip.)
3. THE engine SHALL shard `zombies` and `incidents` like the cards (`zombies/<neighborhood>-<resurrection year>.json`, `incidents/<neighborhood>-<close year>.json`, each with an `index.json` that lists shard, neighborhood, year, size and districts), so that no file the site loads is over about 2 MB compressed (2,000,000 bytes gzip, checked on every exported file including `stats/`). An export with a file over that fails before writing, as in 2.
4. THE first view SHALL load the headline tier only: `points.json` holds headline points and each other tier (`source_unknown`, `city_rereport`, `sensitivity`) is its own file `points/<tier>.json`, which the site loads when the tier is switched on.

### REQ-EXP-PRIV: Block-level privacy for repeat offenders
**Layer:** delight
**User story:** As a resident, I want my home never singled out, so the map shows streets, not houses.
1. WHEN a repeat-offender chain is driven by resident reports (more than half of its re-reports are not city-originated) and its segment is residential or of unknown class, THE engine SHALL export the segment midpoint (or a 100 m grid-cell center if unsnapped) instead of the case point.

### REQ-ING-NIGHTLY: Re-runnable pipeline
**Layer:** credibility
**User story:** As the nightly job, I want one command that rebuilds everything from raw files, so a failed night never corrupts data.
1. `make pipeline` SHALL rebuild all outputs from `$DATA_DIR/raw/` without manual steps, and leave the previous outputs untouched if any stage fails.
2. `make pipeline-sample` SHALL run the same pipeline on `data/sample/` into `$DATA_DIR/processed-sample/`, export to `web/public/data/`, and need no network access. This is a new target: structure.md lists `make pipeline` but not this one, so the owner adds it to structure.md.

### REQ-ING-DL: Reliable downloads
**Layer:** credibility
**User story:** As the owner of a full-data run, I want downloads that survive a bad connection and tell me when the city changed a file, so a run never uses a short or stale file without saying so.
1. EACH download SHALL be tried up to 5 times with exponential backoff (1, 2, 4, 8 s) on network errors, HTTP 408, 425, 429 and 5xx, and short bodies. Other HTTP errors and disk errors SHALL NOT be retried.
2. A partial download SHALL be kept as `<file>.part` and resumed with an HTTP Range request. A server that ignores Range, or a part that does not fit the file, SHALL restart the file from byte 0.
3. THE downloaded size SHALL equal the size the server announced (Content-Length, or the total in Content-Range) before the file is renamed into place.
4. A file already on disk SHALL be kept only when its hash, size and CKAN `last_modified` equal the previous `data/SNAPSHOT.md` row and the server reports the same size. Otherwise it SHALL be fetched again, and a file whose hash differs from the previous row SHALL be reported as CHANGED (console and `$DATA_DIR/logs/download-report.json`).

### REQ-ING-SAMPLE: Committed sample
**Layer:** demo-critical (exists; keep working)
1. `make data-sample` SHALL keep producing `data/sample/sample_311.csv` under 10 MB with the current columns, and its existing tests SHALL keep passing.
