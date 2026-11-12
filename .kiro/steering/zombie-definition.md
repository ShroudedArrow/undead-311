---
inclusion: always
---
# Zombie definition (single source of truth)

All code, agents, and docs must apply these rules exactly. Change parameters only here.

## Scope (in-scope case types)
Only **public right-of-way infrastructure**: potholes and street defects, sidewalks, streetlights, traffic signals and signs, graffiti on public property, missed trash/recycling, abandoned vehicles (final list confirmed from real `type` values during kickoff).
**Out of scope:** case types about people (encampments, needle pickups, welfare checks and similar) and complaints about private residences or businesses. They're excluded from detection and display.

## Pre-registration
These rules and parameters were fixed on the date of the first commit of this file, BEFORE running on full data. Any later change is logged at the bottom with the date and reason.

## Parameters (defaults)
- Matching: **same street segment** (Boston SAM street segments) when both cases snap to a segment within 15 m AND are within `MAX_SEGMENT_DIST = 75` m of each other (long segments must not match opposite ends); otherwise **radius** `RADIUS_M = 30`.
- `WINDOW_DAYS = 60`; maximum incident span `INCIDENT_MAX_SPAN_DAYS = 7`.
- Sensitivity grid (precomputed for the methods page): matching in {segment, radius}, RADIUS_M in {15, 30, 50}, WINDOW_DAYS in {30, 60, 90}.

## Algorithm
1. **Clean:** drop out-of-scope types, invalid/out-of-bounds coordinates, and high-frequency placeholder points (e.g., City Hall 42.3594, -71.0587); count every exclusion.
2. **Incidents (true duplicates only):** a closed case joins an incident only if it matches the incident's location and family AND **was opened before the incident's first closure** (it was reported while the problem was still "alive"), and the incident spans at most `INCIDENT_MAX_SPAN_DAYS` from first open to last close. A case opened AFTER a closure is never a member; it can only be a resurrection. (Grouping by close times alone would swallow a fast resurrection into its own original; a dry run confirmed this bug.) Every closed case belongs to exactly one incident. An incident's close time is its latest member's close time.
3. **Candidate pairs:** (incident I, case R) where `R.open_time > I.close_time`, `R.open_time <= I.close_time + WINDOW_DAYS`, same `type_family`, and matching location. R is not a member of I.
4. **Attribution:** process cases R in time order (ties by case ID). Each R attaches to the **most recent** eligible incident (ties by incident ID). Each R counts once.
5. **Resurrection:** an incident's first attached R is its resurrection; `reports_after` counts every attached R (more reports = stronger evidence). The incident is a **possible zombie** unless step 6 applies.
6. **Planned follow-up (not a zombie):** R is city-originated (`source` in Employee Generated, City Worker App, Maximo Integration, or equivalents in the new system) AND the incident's Coroner label is `made_safe_temporary`, `referred`, or `planned_followup`. A RESIDENT re-report after a "made safe" closure is still a possible zombie, tagged `after_temporary_fix`, so the site can report how often temporary fixes come back.
7. **Chains:** when a resurrection R is later closed, it starts a new incident; if that one resurrects too, the chain grows. `times_risen` counts resurrections at a location chain. Locations with `times_risen >= 3` are **repeat offenders**.
8. **Separate tracking:** incidents labeled `invalid` or `duplicate` are reported separately ("a different kind of death"), not as zombies.
9. **Across systems:** legacy (to Oct 2025) and new-system records match via location, time, and the type crosswalk in `type_families.csv`.

## Confidence score (0 to 1)
Combine: match quality (segment > radius; closer = higher), time gap (shorter = higher), type specificity, Coroner label, local baseline probability (lower chance of coincidence = higher), and surviving Skeptic objections. Document the exact formula in `docs/METHODS.md`.

## Output tables
- `incidents`: `incident_id, member_ids, type_family, department, neighborhood, district, segment_id, close_time, coroner_label`
- `zombies`: `incident_id, resurrection_id, reports_after, gap_days, match_mode, distance_m, baseline_p, confidence, is_planned_followup, after_temporary_fix, chain_id, times_risen, skeptic_notes`

## Language
Always "possible zombie". Measured counts are a floor (a zombie only appears if someone reports again). Never claim the city lied. See `language.md`.

## Change log
| Date | Change | Reason |
|---|---|---|
