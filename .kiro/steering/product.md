---
inclusion: always
---
# Product: The Undead 311

## What we are building
A web app that finds Boston 311 service requests the city marked "closed" that were re-reported at the same place soon after ("possible zombies"), separates real resurrections from coincidence with statistics, and shows them on a haunted map of Boston with an evidence card ("autopsy report") per zombie. It adds a durability metric beside the city's speed metric: **closed on time vs. stayed fixed**.

Full plan: `docs/PROJECT.md`. It is large, so it is NOT always loaded; type `#project` in chat to include it when a task needs the full context.

## Users
Residents who report problems, city councilors and staff, neighborhood associations, local journalists, and 311/department managers.

## Must-have features (build these first)
1. Ingest Boston 311 data (2015 onward) into DuckDB/Parquet; support nightly updates.
2. Zombie detector (rules in `zombie-definition.md`).
3. Comparison baseline + excess resurrections (`methods.md`).
4. Closure-text classification ("Coroner" labels) from a cached label table.
5. Bulk-closure detector.
6. Haunted map with filters (neighborhood, department, case type, year).
7. Autopsy-report evidence cards.
8. "Stayed-fixed on-time rate" per category.
9. Survival curves (how long fixes last).
10. Fair department/neighborhood comparisons (small-sample correction + funnel plots).
11. Methods page (definitions, baseline, validation, limitations).
12. Judge mode: 60-second guided tour of three zombies chosen ONLY from the confirmed validation set, running on the frozen judging snapshot, no login.
13. "Check my street": address/street search from the city's SAM address registry (client-side index, no API).
14. Street-segment matching, incident clustering, zombie chains, and the "repeat offenders" view.
15. "Data as of" date, nightly status, and a "Report an error" link with a public corrections log.

## Should-have
Creatio before/after comparison, interactive methods sliders (precomputed sensitivity grid), share images per zombie/neighborhood, district report cards (print stylesheet), permalinks, Spanish (reviewed by a native speaker), "Night of the Living 311" time-lapse, accessible table view, open dataset download.

## Non-goals
- No user accounts. No runtime LLM API calls in the web app or nightly pipeline (LLM work is done by Kiro agents and cached).
- No individual workers named. No accusations ("possible zombie" only).
- No photo-based verification (photo fields are mostly empty).
- No case types about people and no private-residence complaints (see zombie-definition.md scope).
- No analytics cookies or personal data collection of any kind.
- Privacy in display: on residential streets, repeat offenders driven by resident reports are shown at block level (segment midpoint), not an exact point, so the map never singles out a home.

## Success criteria (Kiroween 2026 judging, 20% each)
Impact, Technological Implementation (Kiro), Design, Innovation, Presentation. Judges may score from the video and write-up without testing, so every feature must be demonstrable in screenshots and in a 3-minute video.
