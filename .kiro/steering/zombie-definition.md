---
inclusion: always
---
# Zombie definition (single source of truth)

All code, agents, and docs must apply these rules exactly. Change parameters only here.

## Scope (in-scope case types)
Only **persistent physical defects** in the public right-of-way: potholes and roadway defects, sidewalks, streetlights, traffic signals, signs, pavement markings, and street fixtures (manholes, utility castings, guardrails, bollards). Recurring-event services produce new events, not resurrections, so they are out.
**Out of scope:** case types about people (encampments, needle pickups, welfare checks and similar) and complaints about private residences or businesses. They're excluded from detection and display.
Sensitivity-only (outside the headline, reported as a sensitivity check): new-system Traffic Signal Request, and unlinked new-system Street Light Other.
**Catch-all successor type:** new-system Street Light Other collects resubmitted potholes, signals, sidewalks and signs, so it has no single family. A Street Light Other case linked from a legacy case ("Resubmitted as / See new case BCS-N") inherits that legacy case's family and tier (`catch_all` flag in `type_families.csv`); if its linked legacy cases disagree, have an unlisted type, or there is no link, it stays sensitivity-only, outside the headline. Because the legacy case was closed as a transfer, the linked case is the same problem continuing, never a re-report of it.
Also out of scope: event-type families (missed trash, graffiti, abandoned vehicles, catch basins, street cleaning, litter, dumping) and inspection or general-request types (Traffic Signal Inspection, Pavement Marking Inspection, General Lighting Request). Types labeled `(Internal)` and work-order types are city-originated and are kept (see step 6).

## Pre-registration
These rules and parameters were fixed on the date of the first commit of this file, BEFORE running on full data. Any later change is logged at the bottom with the date and reason.

## Parameters (defaults)
- Matching: **same street segment** (Boston SAM street segments) when both cases snap to a segment within 15 m AND are within `MAX_SEGMENT_DIST = 75` m of each other (long segments must not match opposite ends); otherwise **radius** `RADIUS_M = 30`.
- `WINDOW_DAYS = 60`; maximum incident span `INCIDENT_MAX_SPAN_DAYS = 7`.
- `MIRROR_WINDOW_HOURS = 6`: a CROSS-SYSTEM pair (legacy to new, or new to legacy) whose open times are within this many hours is a mirror copy, not a resurrection (step 9). Same-system pairs never use this rule; they follow the normal rules (step 3), so a re-report that opens after the original closure stays a possible zombie even within hours.
- Sensitivity grid (precomputed for the methods page): matching in {segment, radius}, RADIUS_M in {15, 30, 50}, WINDOW_DAYS in {30, 60, 90}.

## Algorithm
1. **Clean:** drop out-of-scope types, invalid/out-of-bounds coordinates, and high-frequency placeholder points (the two real placeholder points: 42.3603, -71.0583 and 42.3595, -71.0588); count every exclusion.
2. **Incidents (true duplicates only):** a closed case joins an incident only if it matches the incident's location and family AND **was opened before the incident's first closure** (it was reported while the problem was still "alive"), and the incident spans at most `INCIDENT_MAX_SPAN_DAYS` from first open to last close. A case opened AFTER a closure is never a member; it can only be a resurrection. (Grouping by close times alone would swallow a fast resurrection into its own original; a dry run confirmed this bug.) Every closed case belongs to exactly one incident. An incident's close time is its latest member's close time.
3. **Candidate pairs:** (incident I, case R) where `R.open_time > I.close_time`, `R.open_time <= I.close_time + WINDOW_DAYS`, same `type_family`, and matching location. R is not a member of I.
4. **Attribution:** process cases R in time order (ties by case ID). Each R attaches to the **most recent** eligible incident (ties by incident ID). Each R counts once.
5. **Resurrection:** an incident's first attached R is its resurrection; `reports_after` counts every attached R (more reports = stronger evidence). The incident is a **possible zombie** unless step 6 applies.
6. **Planned follow-up (not a zombie):** R is city-originated (`source` in Employee Generated, City Worker App, Maximo Integration, or equivalents in the new system) AND the incident's Coroner label is `made_safe_temporary`, `referred`, or `planned_followup`. A RESIDENT re-report after a "made safe" closure is still a possible zombie, tagged `after_temporary_fix`, so the site can report how often temporary fixes come back.
   - **Legacy R** is city-originated if `source` is Employee Generated, City Worker App, or Maximo Integration, OR its `type_raw` is an internal or work-order type (`city_originated_type` column in `type_families.csv`: Pothole Repair (Internal), Sidewalk Repair (Internal), StreetLight Pole WO).
   - **New-system R:** no field shows who opened a case (`report_source` is only BOS311, Call, Email; no service name is Internal or a work order; closure codes and comments describe how a case ended). So a new-system R after an original labeled `made_safe_temporary`, `referred`, or `planned_followup` is counted as a possible zombie tagged `source_unknown` and reported separately. The headline count excludes `source_unknown` zombies; they are never silently added to or dropped from it. A new-system R after any other closure label is not affected by this step. Because Transitioned originals are excluded in step 9, the `source_unknown` tag arises only for originals whose label is `made_safe_temporary`, `referred` (by closure text, not by the Transitioned code) or `planned_followup`.
7. **Chains:** when a resurrection R is later closed, it starts a new incident; if that one resurrects too, the chain grows. `times_risen` counts resurrections at a location chain. Locations with `times_risen >= 3` are **repeat offenders**.
8. **Separate tracking:** incidents labeled `invalid` or `duplicate` are reported separately ("a different kind of death"), not as zombies.
9. **Across systems:** legacy (to the 2025 system change) and new-system records match via location, time, and the type crosswalk in `type_families.csv`. Migration mirror rules:
   - A legacy closure labeled transferred or migrated (`TRANSFER_CLOSURE_RE` in `pipeline/undead311/ingest/closure_flags.py`) is never an original: the case continued in the new system.
   - A CROSS-SYSTEM pair (legacy to new, or new to legacy) whose open times are within `MIRROR_WINDOW_HOURS = 6` at the same location and family is a mirror copy of one report, not a resurrection. Same-system pairs never use this rule. Example: a same-system pothole closed 1 h after it opened and re-reported 5 h after the original opened is a possible zombie.
   - Catch-all successor types (`catch_all` = true in `type_families.csv`; currently new-system Street Light Other) take their family and tier per case from the legacy predecessor whose closure text links to them ("Resubmitted as / See new case BCS-N", `TRANSFER_CLOSURE_RE`). The legacy case was closed as a transfer, so the linked case is the same problem continuing, never a re-report of it (a pair with its own predecessor is not a candidate). Its inherited family is used when it is an original or a re-report in later matching against other cases. Predecessors that disagree, an unlisted predecessor type, or no link mean sensitivity-only, outside the headline.
   - A new-system closure with code Transitioned maps to the Coroner label referred (a transfer) and is never an original. Noted closures stay originals (the Coroner records them as closed without a repair). Codes: Resolved and Resolved successfully map to resolved, Noted to noted, Transitioned to referred (`NEW_SYSTEM_CLOSURE_LABELS` in `closure_flags.py`).

## Confidence score (0 to 1)
Combine: match quality (segment > radius; closer = higher), time gap (shorter = higher), type specificity, Coroner label, local baseline probability (lower chance of coincidence = higher), and surviving Skeptic objections. Document the exact formula in `docs/METHODS.md`.

## Output tables
- `incidents`: `incident_id, member_ids, type_family, department, neighborhood, district, segment_id, close_time, coroner_label`
- `zombies`: `incident_id, resurrection_id, reports_after, gap_days, match_mode, distance_m, baseline_p, confidence, is_planned_followup, after_temporary_fix, source_unknown, chain_id, times_risen, skeptic_notes`

## Language
Always "possible zombie". Measured counts are a floor (a zombie only appears if someone reports again). Never claim the city lied. See `language.md`.

## Change log
| Date | Change | Reason |
|---|---|---|
| 2026-11-12 | Scope narrowed to persistent physical defects before any zombie counts were computed; recurring-event services produce new events, not resurrections. | Owner decision |
| 2026-11-12 | Added migration mirror rules (step 9) and `MIRROR_WINDOW_HOURS = 6`: transferred or migrated legacy closures are never originals; cross-system pairs opened within 6 h are mirror copies. | Owner decision; evidence in docs/DECISIONS.md |
| 2026-11-12 | Step 6 detection text added; new-system re-reports after made-safe, referred or planned-follow-up closures are tagged `source_unknown` and reported outside the headline; `source_unknown` column added to `zombies`. | Owner decision; new system has no origin field |
| 2026-11-12 | Mirror window (step 9, MIRROR_WINDOW_HOURS) restricted to cross-system pairs; same-system pairs follow the normal rules. | Owner decision |
| 2026-11-12 | Step 9: new-system closure code Transitioned maps to the referred label and is never an original; Noted closures stay originals. | Owner decision; evidence in docs/DECISIONS.md |
| 2026-11-12 | Scope: new-system Traffic Signal Request moved from the headline scope to sensitivity-only; Street Light Other stays in scope. A sensitivity run without Street Light Other (a migration catch-all) must be made when the detector exists; the sensitivity tier is a data label only until the detector reads it. | Owner rule applied to link crosswalk and closure-comment sample; evidence in docs/DECISIONS.md |
| 2026-11-12 | Catch-all successor types get their family from the linked predecessor; the link rule alone misclassified a catch-all. Street Light Other: linked cases inherit the legacy case's family (a continuation, never a re-report of that legacy case); unlinked ones are sensitivity-only. Supersedes "Street Light Other stays in scope" above. | Owner decision; evidence in docs/DECISIONS.md |
| 2026-11-12 | Clarification (not a rule change): step 1 example of high-frequency placeholder points replaced by the two real points. | Stale example |
| 2026-11-12 | `type_families.csv`: added 7 legacy types as `excluded` (Encampments, Equipment Repair, General Comments For a Program or Policy, Improper Storage of Trash (Barrels), Parks Lighting/Electrical Issues, Public Works General Request, Transportation General Request). They are the only predecessors of 37 linked Street Light Other cases, which now inherit an excluded tier (out of scope) instead of falling to sensitivity-only as unlisted. Headline scope unchanged (160 linked core cases); made before any zombie counts. | Crosswalk completeness; evidence in docs/DECISIONS.md |
