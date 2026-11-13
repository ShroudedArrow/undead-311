# Test town worksheet

For the project owner. Kiro drafted the cases in `pipeline/tests/fixtures/test_town.csv` (regenerate with `make test-town`); **you** write `pipeline/tests/fixtures/expected_zombies.json` by hand from `zombie-definition.md`, before any detector code exists. Agents can't edit that file (the guard hook blocks it).

How to use it: for each scenario, read the cases in the CSV (the `note` column says what each one is), apply the rules, and fill in the expected-result line. Then copy your answers into `expected_zombies.json` in the format below.

Fixture conventions (also in the zombie-engine design):
- Rows are in the normalized schema BEFORE family resolution: the engine derives `type_family`, `scope_tier`, catch-all inheritance and `predecessor_ids` from `type_families.csv` and the closure texts.
- `segment_id` / `segment_snap_m` are pre-snapped street segments (blank = no segment within 15 m), so the fixture doesn't need the SAM layer.
- `coroner_label` is given per closed case, so your answer doesn't depend on the label table.
- Each scenario sits at its own spot, at least 800 m from every other, so scenarios can't interact. Defaults: RADIUS_M = 30, WINDOW_DAYS = 60, INCIDENT_MAX_SPAN_DAYS = 7, MAX_SEGMENT_DIST = 75, MIRROR_WINDOW_HOURS = 6.
- Incident IDs are the smallest member case ID (string order), so you can name incidents without running code.

## Format for expected_zombies.json

```json
{
  "fixture": "pipeline/tests/fixtures/test_town.csv",
  "written_by": "<your name>, by hand, <date>",
  "zombies": [
    {"incident_id": "<smallest member id>", "member_ids": ["..."], "resurrection_id": "...", "reports_after": 1,
     "match_mode": "segment | intersection | radius", "tier": "headline | source_unknown | sensitivity",
     "after_temporary_fix": false, "chain_id": "<incident_id of the chain start>", "times_risen": 1}
  ],
  "planned_followups": [{"incident_id": "...", "resurrection_id": "..."}],
  "separate_deaths": [{"incident_id": "...", "label": "invalid | duplicate", "rereport_id": "..."}],
  "repeat_offenders": [{"chain_id": "...", "times_risen": 3}],
  "excluded_ids": {"placeholder_or_invalid_coords": ["..."], "out_of_scope_type": ["..."]},
  "incidents_with_several_members": [{"incident_id": "...", "member_ids": ["..."]}]
}
```

List every possible zombie in `zombies`, including `source_unknown` and sensitivity ones (the `tier` field says which). Anything not listed is asserted NOT to be a zombie. The golden test compares lists sorted by `incident_id`.

## S01. True zombies, one per system

Cases: `101099001001`, `101099001002`, `BCS-00901003`, `BCS-00901004`

Rule tested: Steps 3-5: a closed case, then a same-family report at the same place that opens after the closure and within WINDOW_DAYS = 60.

Expected result: ______________________________________________

## S02. Coincidences outside the window or radius

Cases: `101099002001`, `101099002002`, `101099002003`, `101099002004`

Rule tested: Step 3 limits: WINDOW_DAYS = 60 (one pair re-reported 61 days after closure) and RADIUS_M = 30 when there is no segment (one pair 45 m apart).

Expected result: ______________________________________________

## S03. Duplicate reports form one incident

Cases: `101099003001`, `101099003002`, `101099003003`, `101099003004`

Rule tested: Step 2: cases opened before the incident's first closure, same family and place, span at most INCIDENT_MAX_SPAN_DAYS = 7, are one incident. Decide the incident's members, its close time, and what the later report is.

Expected result: ______________________________________________

## S04. Planned follow-up after a made-safe or referred closure

Cases: `101099004001`, `101099004002`, `101099004003`, `101099004004`

Rule tested: Step 6: a city-originated R (by `source`, or by an internal/work-order `type_raw`) after a `made_safe_temporary`, `referred` or `planned_followup` label.

Expected result: ______________________________________________

## S05. Three-time repeat offender

Cases: `101099005001`, `101099005002`, `101099005003`, `101099005004`

Rule tested: Steps 4 and 7: each R attaches to the most recent eligible incident; a resurrection that closes starts a new incident; `times_risen >= 3` is a repeat offender.

Expected result: ______________________________________________

## S06. Placeholder and invalid coordinates

Cases: `101099006001`, `101099006002`, `101099006004`, `BCS-00906003`

Rule tested: Step 1: the two placeholder points (42.3603, -71.0583 and 42.3595, -71.0588) and out-of-bounds coordinates are dropped and counted.

Expected result: ______________________________________________

## S07. Out-of-scope types

Cases: `101099007001`, `101099007002`, `101099007003`, `101099007004`

Rule tested: Scope: event types (graffiti) and people-related types (Encampments) are excluded from detection.

Expected result: ______________________________________________

## S08. Pairs spanning the 2025 system change

Cases: `101099008001`, `101099008003`, `BCS-00908002`, `BCS-00908004`

Rule tested: Step 9: legacy and new-system records match through the type crosswalk (pothole to Pothole, Sign Repair to Damaged/Faded Sign); the opens are days apart, so the mirror rule does not apply.

Expected result: ______________________________________________

## S09. Fast resurrection vs. a true duplicate

Cases: `101099009001`, `101099009002`, `101099009003`, `101099009004`

Rule tested: Step 2 and property 18: a case opened AFTER the first closure is never an incident member. One pair opens the next day; the contrast pair opens before the first closure.

Expected result: ______________________________________________

## S10. Opposite ends of one long street segment

Cases: `101099010001`, `101099010002`, `101099010003`, `101099010004`

Rule tested: Matching: same segment requires both snaps within 15 m AND MAX_SEGMENT_DIST = 75 m; otherwise RADIUS_M = 30. One pair is 300 m apart on one segment; the contrast pair is 60 m apart on one segment.

Expected result: ______________________________________________

## S11. Resident re-report after a made-safe closure

Cases: `101099011001`, `101099011002`, `101099011003`, `101099011004`

Rule tested: Step 6: a RESIDENT R after `made_safe_temporary` is still a possible zombie, tagged `after_temporary_fix`.

Expected result: ______________________________________________

## S12. Legacy closed as transferred and recreated in the new system

Cases: `101099012001`, `101099012003`, `BCS-00912002`, `BCS-00912004`

Rule tested: Step 9: a transfer or migration closure (`TRANSFER_CLOSURE_RE`) is never an original. One transfer links its successor by BCS number; the other has no link.

Expected result: ______________________________________________

## S13. New-system re-report with unknown source

Cases: `BCS-00913001`, `BCS-00913002`, `BCS-00913003`, `BCS-00913004`

Rule tested: Step 6 (new system): a new-system R after `made_safe_temporary`, `referred` (by closure text) or `planned_followup` is tagged `source_unknown`, outside the headline.

Expected result: ______________________________________________

## S14. Mirror copies

Cases: `101099014001`, `101099014004`, `BCS-00914002`, `BCS-00914003`

Rule tested: Step 9: a CROSS-SYSTEM pair opened within MIRROR_WINDOW_HOURS = 6 at the same place and family is one report, in either direction (legacy then new, new then legacy).

Expected result: ______________________________________________

## S15. Same-system fast re-reports

Cases: `101099015001`, `101099015002`, `BCS-00915003`, `BCS-00915004`

Rule tested: Step 9: the mirror rule is cross-system only. A pothole closed 1 h after opening and re-reported 5 h after the original opened, in the same system (one pair per system).

Expected result: ______________________________________________

## S16. New-system Transitioned vs. Noted closures

Cases: `BCS-00916001`, `BCS-00916002`, `BCS-00916003`, `BCS-00916004`

Rule tested: Step 9: closure code Transitioned maps to `referred` and is never an original; Noted stays an original.

Expected result: ______________________________________________

## S17. Catch-all inheritance (linked Street Light Other)

Cases: `101099017001`, `BCS-00917002`, `BCS-00917003`

Rule tested: Scope and step 9: a Street Light Other case linked from a legacy case ("Resubmitted as BCS-N") inherits that case's family and tier; it is never a re-report of its own predecessor, and its inherited family is used in later matching.

Expected result: ______________________________________________

## S18. Sensitivity tier: unlinked catch-all and Traffic Signal Request

Cases: `BCS-00918001`, `BCS-00918002`, `BCS-00918003`, `BCS-00918004`

Rule tested: Scope: unlinked Street Light Other and Traffic Signal Request are sensitivity-only, outside the headline (available as a toggle).

Expected result: ______________________________________________

## S19. Invalid and duplicate closures (extra, step 8)

Cases: `101099019001`, `101099019002`, `101099019003`, `101099019004`

Rule tested: Step 8: incidents labeled `invalid` or `duplicate` are reported separately ("a different kind of death"), not as zombies. Not in testing.md's list; added because step 8 had no fixture case.

Expected result: ______________________________________________
