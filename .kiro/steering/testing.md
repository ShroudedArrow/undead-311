---
inclusion: always
---
# Testing and definition of done

## Definition of done for every task
1. `make test` passes (Python + TypeScript, including property tests).
2. `ruff check` clean; TypeScript compiles with no errors.
3. New behavior has tests that cite requirement IDs.
4. A one-line entry is added to `docs/KIRO_LOG.md` (see `kiro-log.md`).

## Required property-based tests (hypothesis / fast-check)
1. A case is never its own zombie.
2. A resurrection always opens strictly after the original's closure.
3. All rates are within [0, 1].
4. Increasing RADIUS_M or WINDOW_DAYS never removes a candidate pair (final zombie counts may change when incidents merge; do not assert monotonic counts).
5. Results are invariant to input row order.
6. Survival curves start at 1 and are non-increasing.
7. Excess counts are reproducible for a fixed random seed.
8. Shrunk group rates lie between the raw group rate and the citywide rate.
9. Coroner output is always in the allowed label set.
10. Stayed-fixed rate ≤ on-time rate.
11. Distance is symmetric and non-negative.
12. Incident clustering is a partition: every closed in-scope case belongs to exactly one incident.
13. Every re-report is attributed to at most one incident; attribution is deterministic (ties by ID).
14. Metamorphic: translating every case by the same small offset, or shifting every timestamp by the same amount, leaves zombie counts unchanged.
15. Metamorphic: duplicating a closed case (same place, type, close time) never increases the zombie count.
16. Contract: every exported file validates against its JSON Schema in `/schemas/`; the web app's parsers accept every valid file.
17. The adjusted stayed-fixed rate is clamped so it never exceeds the on-time rate.
18. A case opened after an incident's first closure is never a member of that incident (prevents fast resurrections from vanishing).

## Golden fixture: "test town" (build this first)
A fixture of about 30 cases (2–4 per scenario), `pipeline/tests/fixtures/test_town.csv`, where the right answer is known in advance: true zombies, coincidences outside the window, duplicate reports that must form one incident, a planned follow-up after a "made safe" closure, a three-time repeat offender, a placeholder-coordinate case, an out-of-scope case type, a pair spanning the October 2025 system change, a **fast resurrection** (re-reported the next day and closed within 3 days), two cases at opposite ends of one long street segment (must NOT match), and a resident re-report after a "made safe" closure. `expected_zombies.json` lists the exact expected output. The detector must reproduce it exactly. This is the correctness anchor for the one-shot build. **Kiro may draft the CASES from the scenario list, but a person (the project owner) works out `expected_zombies.json` by hand from this definition BEFORE any detector code exists.** If an agent writes both the code and the expected answer, the test proves nothing. Agents may not edit it (the guard hook blocks it).

## CI is the independent judge (agents don't grade their own work)
Every pull request runs, in GitHub Actions: all tests, the test-town golden check, schema validation, `make copy-lint`, an automated accessibility scan (axe via Playwright) of judge mode, and a bundle-size budget. A nightly CI job runs the property tests with a deep Hypothesis profile (10x examples, saved example database) to hunt rare failures. CI posts a one-line result to the agent channel.

## Test data
Use `data/sample/` (committed). Property tests generate synthetic cases; keep them fast (< 60 s total). Mark slow full-data checks with `@pytest.mark.slow`.
