# Design: zombie-engine

## Overview
A Python package (`pipeline/undead311`, Python 3.11, uv) that runs ingest, Coroner join, detection, scoring and export. Heavy lifting runs as SQL in DuckDB (load, normalize, crosswalk, candidate edges through a grid-bucket join). The order-dependent rules (incidents, attribution, chains) run as small deterministic Python passes over sorted candidate edges. The detector core is a **pure function**, `detect(cases, params) -> DetectionResult`. The test town, the property tests and the full-data run all call the same function, so the rules exist in exactly one place.

Existing code is reused, not rewritten: `ingest/times.py` (REQ-ING-TZ) and `ingest/closure_flags.py` (`is_transferred_original`, `is_mirror_pair`, `extract_linked_case_id`, `resolve_catch_all`, `pair_survives`, REQ-DET-2 and REQ-ING-CATCH). `pair_survives` does not check time order; the detector adds the strict "re-report opens after the closure" check itself (REQ-DET-2.1). Until now that check existed only in a test helper (`timeline_pair_survives`).

## Architecture
```
$DATA_DIR/raw/*.csv ─► ingest.load (DuckDB) ─► ingest.normalize ─► ingest.crosswalk (+catch-all) ─► ingest.clean ─► ingest.snap
                                                                                                         │
                         data/labels/coroner_labels.csv ─► coroner.join ◄── coroner.templates ◄─────────┤
                                                                                                         ▼
                                        detect.edges (SQL grid join) ─► detect.core.detect() (pure Python)
                                                                                                         │
                     data/labels/skeptic_objections.json ─► detect.skeptic ─► detect.confidence ◄────────┤
                                                                                                         ▼
                                                export.* (schema-validated, sorted, data_version) ─► web/public/data/
```

### Modules and interfaces
| Module | Responsibility | Key interface | Requirements |
|---|---|---|---|
| `paths.py` | DATA_DIR resolution with fallback; worktree-safe repo root | `data_dir() -> Path`, `repo_root() -> Path` | REQ-ING-PATH |
| `ingest/load.py` | Raw CSVs into DuckDB tables `raw_legacy`, `raw_new`; row counts | `load(con, raw_dir) -> LoadReport` | REQ-ING-1 |
| `ingest/normalize.py` | One SQL view `cases_norm` in the normalized schema; time conversion through a DuckDB Python UDF that calls `times.to_utc_and_local` | `normalize(con)` | REQ-ING-2, REQ-ING-TZ |
| `ingest/crosswalk.py` | Join `type_families.csv`; links; catch-all inheritance | `apply_crosswalk(con)`, `link_table(con) -> dict` | REQ-ING-XWALK, REQ-ING-CATCH |
| `ingest/clean.py` | Bounds, placeholders, candidate placeholder report, exclusion counts | `clean(con) -> Exclusions` | REQ-ING-CLEAN |
| `ingest/snap.py` | Snap to SAM segments (DuckDB `spatial` if available, else a Python segment-distance pass over a grid index); derive the `intersections` table (segment endpoints shared by 2+ segments at one z-level) and each snapped case's `near_node_ids` within INTERSECTION_M | `snap(con, segments_path or None)` | REQ-ING-SNAP |
| `ingest/pii.py` | Regex scrub of free text | `scrub(text) -> (text, counts)` | REQ-ING-PII |
| `coroner/templates.py` | Mask and deduplicate closure texts | `build_templates(con) -> Path` | REQ-COR-1.1 |
| `coroner/join.py` | Label precedence; `unlabeled` count; allowed-set check | `join_labels(con, labels_csv)` | REQ-COR-1.2–1.4 |
| `coroner/eval.py` | Accuracy vs hand labels | `evaluate(labels, hand) -> EvalReport` | REQ-COR-EVAL |
| `detect/params.py` | Frozen `Params` dataclass, defaults from zombie-definition.md | `Params(...)`, `DEFAULT` | REQ-DET-PARAM |
| `detect/match.py` | Haversine; segment / intersection / radius rule; grid cell key | `distance_m(a, b)`, `matches(a, b, p) -> MatchMode or None` | REQ-DET-MATCH |
| `detect/edges.py` | SQL candidate edges (member edges within INCIDENT_MAX_SPAN_DAYS; re-report edges within WINDOW_DAYS), same family, grid neighbors | `edges(con, p) -> list[Edge]` | REQ-DET-MATCH.4 |
| `detect/core.py` | Pure detector: incidents, pairs, attribution, classification, tiers, chains, separate deaths | `detect(cases: Sequence[Case], p: Params, edges=None) -> DetectionResult` | REQ-DET-1, -2, -3, -PF, -TIER, -CHAIN, -SEP |
| `detect/bulk.py` | Bulk-closure groups: same department, day and template, at least BULK_MIN_CASES cases and at least BULK_RATIO times the department's median daily count for that template | `bulk_closures(con, p)` | REQ-BULK |
| `detect/confidence.py` | Score and `confidence_partial` | `confidence(z, ctx) -> float` | REQ-CONF |
| `detect/skeptic.py` | Skeptic input/output files | `write_input(...)`, `join(...)` | REQ-SKEP |
| `detect/grid.py` | Sensitivity runs | `run_grid(cases, edges_fn) -> GridResult` | REQ-SENS-RUN |
| `export/*` | Schema validation (`jsonschema`), deterministic JSON writers, cards, columnar points, sizes, `.gz` | `export_all(result, out_dir)` | REQ-EXP-1, -SIZE, -PRIV |
| `cli.py` | `python -m undead311 pipeline [--sample]`, atomic DuckDB write | `main()` | REQ-ING-NIGHTLY, REQ-EXP-1.4 |
| `fixtures.py` | Test-town loader: reads RAW fixture rows into the `cases_norm` table, then runs the normal crosswalk, catch-all, clean and detect path. Uses pre-snapped segments and `coroner_label`; ignores `scenario`/`note` | `load_test_town(con, path)`, `golden_result(result, excluded) -> dict` (the worksheet format) | REQ-DET-GOLD |

`detect.core.detect()` takes optional precomputed edges. Without them, it computes edges by brute force (used for small inputs in tests). A test checks that the SQL edge generator and the brute-force generator agree on `data/sample` (REQ-DET-MATCH.4).

## Algorithm (exactly ZD steps 1–9)
1. **Incidents** (REQ-DET-1): sort closed in-scope cases by (`open_time_utc`, `id`). For each case c, the candidate incidents are those where c matches some member's location and family, `c.open < min(member.close)`, and `max(close ∪ c.close) − min(open) <= INCIDENT_MAX_SPAN_DAYS`. Join the one with the smallest incident ID, or start a new incident. Incident `close_time` = max member close. `coroner_label` = the label of the member with that close (ties by member ID). `id` = min member ID. Open (unclosed) cases are never members.
2. **Candidate pairs** (REQ-DET-2): first, drop every mirror R. That is any R with a cross-system closed in-scope case of the same family at a matching location opened within MIRROR_WINDOW_HOURS; a mirror is one report and is attached nowhere. Then, for each remaining case R (any status) and incident I, keep (I, R) when `R.open > I.close` (strict), `R.open <= I.close + WINDOW_DAYS`, same family, R matches any member, R not a member, no member of I is a transferred original, and R's `predecessor_ids` contains no member of I. A linked successor can still be a re-report of a *different* incident, which keeps the existing test `test_linked_successor_is_candidate_for_a_different_original`. Excluded pairs are counted by reason.
3. **Attribution** (REQ-DET-3): process R in (`open_time_utc`, `id`) order. Attach R to the eligible incident with max `close_time`, ties by min incident ID. Each R attaches once.
4. **Classification** (REQ-DET-PF, -SEP): resurrection = earliest attached R; step 6 is applied to the resurrection only. Labels `invalid`/`duplicate` go to `separate_deaths`. Planned follow-up: legacy city-originated R plus label in {made_safe_temporary, referred, planned_followup}. Possible zombie otherwise; flags `after_temporary_fix` (legacy resident R plus made_safe_temporary) and `source_unknown` (new-system R plus one of the three labels).
5. **Tier** (REQ-DET-TIER): `sensitivity` if the incident (any member) or the resurrection has scope tier `sensitivity`; else `source_unknown` if flagged; else `headline`.
6. **Chains** (REQ-DET-CHAIN): when I is a possible zombie and its resurrection R is closed, R is a member of some incident J (R opened after I closed, so J ≠ I). Link I → J. Planned follow-ups and separate deaths don't link. Chains are the resulting paths. `chain_id` = first incident ID. `times_risen` = the chain's total of possible zombies (all tiers), the same on every record. Repeat offender = at least 3 headline zombies in the chain.

**Interpretations recorded in docs/DECISIONS.md:**
- Matching follows zombie-definition.md (owner decision, change log 2026-11-13): segment (same segment, both snapped, at most 75 m apart); else intersection (both snapped to different segments, each within 15 m of the same shared segment endpoint); else radius (at most 30 m), but ONLY when at least one case is unsnapped. Two snapped cases on different segments never match by radius.
- Intersections come from the SAM geometry: the Boston Street Segments file has LineStrings and no node IDs, so an intersection is a first or last vertex shared by two or more segments (6-decimal coordinates, same `F_ZLEV` / `T_ZLEV`). In the 2026-11-13 file, 11,802 of 13,828 distinct endpoints are shared (85%); the rest are dead ends. Known limitation, stated on the methods page: not every shared endpoint is a cross street.
- Tier precedence: `sensitivity` over `source_unknown` over `headline`. Each zombie keeps both flags, so nothing is lost.
- An incident's Coroner label is the label of its latest-closing member. That is the closure that ended it.
- If any member of an incident is a transferred original, the whole incident is never an original. This is the conservative reading: counts are a floor.
- An incident's location is the set of its members' locations (R matches if it matches any member).

## Data models
```python
@dataclass(frozen=True)
class Case:            # normalized, after crosswalk and cleaning
    id: str; system: Literal["legacy","new"]; open_utc: datetime; close_utc: datetime | None
    type_raw: str; type_family: str; scope_tier: Literal["core","sensitivity"]
    city_originated_type: bool; predecessor_ids: tuple[str, ...]
    source: str | None; closure_text: str | None; closure_code: str | None; coroner_label: str | None
    lat: float; lon: float; segment_id: str | None; segment_snap_m: float | None
    near_node_ids: frozenset[str]   # intersections within INTERSECTION_M; empty without segment geometry
    department: str | None; neighborhood: str | None

@dataclass(frozen=True)
class Zombie:
    incident_id: str; member_ids: tuple[str, ...]; resurrection_id: str; reports_after: int; gap_days: float
    match_mode: Literal["segment","intersection","radius"]; distance_m: float; tier: Literal["headline","source_unknown","sensitivity"]
    after_temporary_fix: bool; source_unknown: bool; chain_id: str; times_risen: int
    baseline_p: float | None; confidence: float; confidence_partial: bool
    skeptic_verdict: Literal["survives","weakened","explained_away","not_reviewed"]; skeptic_notes: str
```
`DetectionResult` holds `incidents`, `zombies`, `planned_followups`, `separate_deaths`, `repeat_offenders`, and `excluded_pairs` (counts by reason).

### Exported files (each has a JSON Schema in `/schemas/`)
`zombies.schema.json` (all tiers), `points.schema.json` (columnar: parallel arrays of id, lat, lon, tier, family, department, neighborhood, year), `card.schema.json` (one shard = list of cards with both case records, scrubbed text, label, gap, dates, confidence, Skeptic), `exclusions.schema.json` (counts and excluded IDs by reason), `separate_deaths.schema.json`, `repeat_offenders.schema.json`, `bulk_closures.schema.json`, `status.schema.json` (`data_version`, last run, row counts, anomalies, `segments` availability), and `test_town_expected.schema.json`, which validates the owner's answer key format (docs/TEST_TOWN_WORKSHEET.md).

### Confidence formula (proposal; frozen in docs/METHODS.md before the first full-data run, REQ-CONF)
`confidence = clamp01(0.20·match + 0.15·gap + 0.10·specificity + 0.15·label + 0.30·baseline + 0.10·skeptic)`
- **match:** segment mode `1 − d/(2·MAX_SEGMENT_DIST)`; intersection mode `0.7·(1 − d/(2·INTERSECTION_M))` where d is the sum of the two distances to the intersection; radius mode `0.8·(1 − d/RADIUS_M)`. The intersection weight is a proposal like the others in this formula.
- **gap:** `1 − gap_days/WINDOW_DAYS`.
- **specificity:** 1 for a specific type; 0.7 for an inherited catch-all.
- **label:** resolved 1, made_safe_temporary 0.9, noted 0.8, referred 0.7, planned_followup 0.6, other 0.6, bulk_backlog 0.5. invalid and duplicate never reach scoring (separate deaths). If `bulk_closure` is set, the term is min(label, 0.5).
- **baseline:** `1 − baseline_p` (neutral 0.5 until durability-stats provides `baseline_p`).
- **skeptic:** survives 1, weakened 0.5, explained_away 0, not_reviewed 0.5.

Weights are not yet approved by the owner; they stay marked "pending owner approval" in METHODS.md.

## Correctness properties
Each property becomes one Hypothesis test named `test_prop_<n>_<slug>` with a docstring citing the requirement IDs. Generators build small towns: 1 to 3 straight streets split into segments, 2 to 40 cases, both systems, all families and tiers, times around DST changes, all closure labels and sources. The fast profile is about 200 examples (whole suite < 60 s); the deep profile (nightly) is 10× with a saved example database.

| # | Property | testing.md | Requirements |
|---|---|---|---|
| P1 | A case is never its own zombie: `resurrection_id ∉ member_ids` | 1 | REQ-DET-2.1 |
| P2 | Every attached R opens strictly after its incident's close (UTC) | 2 | REQ-DET-2.1, REQ-ING-TZ.3 |
| P3 | Increasing RADIUS_M or WINDOW_DAYS never removes a candidate pair. Pair identity is case level: (original case m, re-report R) with `R.open > m.close`, same family, matching location, within the window, before incident grouping. Zombie counts are not asserted monotonic | 4 | REQ-DET-MATCH, REQ-DET-2 |
| P4 | Results (incidents, zombies, exports) are invariant to input row order | 5 | REQ-ING-2.3, REQ-EXP-1.3 |
| P5 | Every Coroner label after the join is in the allowed set; unknown labels are rejected | 9 | REQ-COR-1.4 |
| P6 | Distance is symmetric and non-negative; `distance(a, a) = 0` | 11 | REQ-DET-MATCH.4 |
| P7 | Incidents partition the closed in-scope cases (each in exactly one) | 12 | REQ-DET-1.1 |
| P8 | Each R is attached to at most one incident; detect() on the same input gives the same attribution | 13 | REQ-DET-3 |
| P9 | Metamorphic: translating all cases by the same small offset (staying in bounds and away from placeholders, segments unchanged), or shifting all times by the same amount, leaves zombie counts per tier unchanged | 14 | REQ-DET-1, -2, -3 |
| P10 | Metamorphic: duplicating a closed case (same place, type, open and close time, new ID) never increases the zombie count | 15 | REQ-DET-1, -3 |
| P11 | Contract: every exported file validates against its schema; invalid files are refused (the web half of #16 is in haunted-web) | 16 | REQ-EXP-1.1 |
| P12 | A case opened at or after an incident's earliest member close is never a member of it | 18 | REQ-DET-1.4 |
| P13 | Cross-system ordering is correct across DST changes (existing `pipeline/tests/property/test_dst_ordering.py`, kept) | 19 | REQ-ING-TZ |
| P14 | Per pair: an (I, R) where R is a cross-system mirror of a member of I, or I has a transferred member, is never a zombie pair; a mirror R is attached to no incident; same-system pairs are never mirrors; a Transitioned original never yields a zombie | 20 | REQ-DET-2.2, REQ-DET-2.4 |
| P15 | A linked successor is never a re-report of its own predecessor's incident | owner (new) | REQ-DET-2.3, REQ-ING-CATCH.5 |
| P16 | An unlinked or ambiguous catch-all case never enters the headline (as original or re-report) | owner (new) | REQ-DET-TIER.4, REQ-ING-CATCH.3 |
| P17 | Every possible zombie has exactly one tier, and the headline count equals the number of `headline` zombies | — | REQ-DET-TIER.1–2 |
| P18 | A legacy city-originated R after made_safe/referred/planned never makes a possible zombie; a legacy resident R after made_safe always carries `after_temporary_fix`; a new-system R after those labels always carries `source_unknown` | — | REQ-DET-PF |
| P19 | Confidence is always within [0, 1], and `confidence_partial` is true exactly when a term is neutral | — | REQ-CONF.1–2 |
| P20 | PII scrub is idempotent and removes every generated email and phone number | — | REQ-ING-PII.1 |
| P21 | Matching rule: two snapped cases on different segments match only in `intersection` mode (both within INTERSECTION_M of one shared endpoint); two snapped cases are never matched by `radius` mode; a pair with an unsnapped case is matched only by `radius` mode. Generated small towns include crossing streets, a street split mid-block, a dead end and an overpass (different z-levels) | owner (new) | REQ-DET-MATCH.1–3, REQ-ING-SNAP.4 |
| P22 | Matching is symmetric: `matches(a, b)` and `matches(b, a)` give the same mode and distance | 11 | REQ-DET-MATCH.4 |

The **golden test** (REQ-DET-GOLD) is example-based: it reproduces `expected_zombies.json` exactly. The existing unit tests in `test_closure_flags.py`, `test_times.py` and `test_sample.py` stay unchanged.

## Error handling
- Missing raw file: stop with the file name and `make data-download`. A missing segments file means radius-only matching plus a status flag. A missing Coroner labels file means label `other`, plus an `unlabeled` share in the run report and status.
- Schema validation failure: the run fails before writing. The previous files stay in place (REQ-ING-NIGHTLY.1).
- An unparseable value becomes null and is counted by reason, never dropped silently.
- Any parameter mismatch with zombie-definition.md fails the test suite (REQ-DET-PARAM.3).

## Testing strategy
- **Unit tests per module**, each citing its requirement IDs in the test name or docstring.
- **Property tests** P1–P22, using a Hypothesis `fast` profile for `make test` and a `deep` profile for nightly CI.
- **Golden test** on the test town.
- **Equivalence test:** the SQL edge generator matches brute force on `data/sample`.
- `@pytest.mark.slow` marks full-data checks.

New dependencies: `jsonschema` (contracts). If DuckDB `spatial` is unavailable, segment snapping uses `shapely`. Each new dependency is noted in the PR description.
