# Tasks: haunted-web

Layer tags drive the build order: all `[demo-critical]` tasks in every spec first, then `[credibility]`, then `[delight]`. Definition of done per task: `make test` passes (vitest and fast-check included), TypeScript compiles with no errors, tests cite requirement IDs, one line in docs/KIRO_LOG.md. Human-written copy stays `TODO-COPY:`; never invent it.

## Demo-critical

- [x] 1. [demo-critical] App scaffold, tokens, fonts and copy
  - Vite + React + TS in `web/` (pinned in `package-lock.json`), `npm test` = vitest, `make build`, `make e2e` wiring; `styles/tokens.css` with the six palette colors only; self-hosted Public Sans and Courier Prime; `copy/en.json` plus typed `t()`; footer text, OSM credit, data licenses; "Data as of" from `status.json`.
  - _Requirements: REQ-WEB-COPY.1–3, REQ-WEB-DESIGN.1–3, REQ-WEB-FRESH.1_
- [x] 2. [demo-critical] Schema-derived parsers and fixtures
  - Generate types from `/schemas/`; ajv standalone validators (CSP-safe); per-panel error states; fixture files from `data/sample/` that follow the schemas until real exports exist.
  - [x] 2.1 Property W1: parsers accept every schema-valid generated file and reject files missing a required field. _REQ-WEB-DATA.1; testing.md #16_
  - _Requirements: REQ-WEB-DATA.1–3_
- [x] 3. [demo-critical] Filtering and aggregation library
  - `lib/filter.ts` (`applyFilters`, `aggregate`), `TierMode`.
  - [x] 3.1 Property W2: the filter result is a subset; empty filters with `all` return the input. _REQ-WEB-MAP.2_
  - [x] 3.2 Property W3: filters commute and are idempotent. _REQ-WEB-MAP.3_
  - [x] 3.3 Property W5: aggregate counts sum to the filtered total and are never negative. _REQ-WEB-MAP.2_
  - _Requirements: REQ-WEB-MAP.2–4_
- [x] 4. [demo-critical] Haunted map
  - MapLibre with a self-hosted Boston PMTiles extract restyled to the palette (no default dark style); deck.gl IconLayer with a 3–5 sprite atlas (placeholder sprites until the owner's spray-paint scans exist; record that in the PR); filters UI; count; OSM attribution.
  - _Requirements: REQ-WEB-MAP.1–5_
- [x] 5. [demo-critical] Table view
  - Sortable table with the same set as the map; each row opens the card.
  - [x] 5.1 Property W4: map set = table set = counted set for any filters and tier mode. _REQ-WEB-MAP.3, REQ-WEB-TABLE.1_
  - _Requirements: REQ-WEB-TABLE.1_
- [x] 6. [demo-critical] Autopsy card
  - Triplicate form, stamps, typewriter face inside the form only, both case records, Skeptic section, `partial` confidence note, bulk-closure warning, phone bottom sheet, lazy shard loading.
  - _Requirements: REQ-WEB-CARD.1–6_
- [x] 7. [demo-critical] Two-number scorecard
  - On-time next to stayed-fixed with intervals and n; label says raw or adjusted.
  - _Requirements: REQ-WEB-SCORE.1–2_
- [x] 8. [demo-critical] Judge mode
  - 60-second tour from `judge_tour.json`: skip, pause, keyboard, reduced motion; provisional notice; `scripts/check-tour.ts` enforced by `make build JUDGING=1`.
  - [x] 8.1 Property W8: a judging build accepts a tour only if every ID is confirmed. _REQ-WEB-JUDGE.2_
  - _Requirements: REQ-WEB-JUDGE.1–4_
- [x] 9. [demo-critical] Accessibility floor
  - Focus styles, keyboard paths, contrast rules (no pink or orange text), color never the only signal, reduced motion; axe scan inside `make e2e`.
  - _Requirements: REQ-WEB-A11Y.1–2_
- [x] 10. [demo-critical] Payload and origin checks
  - Build script that measures first-view transfer size (warning for now) and fails on any non-same-origin URL in the built output.
  - _Requirements: REQ-WEB-PERF.1–2_
- [x] 11. [demo-critical] End-to-end judge-mode test
  - Playwright on phone and desktop viewports, keyboard only, reduced motion on and off; screenshots for reviewer-ux.
  - _Requirements: REQ-WEB-TEST.1–2_

## Credibility

- [x] 12. [credibility] Content Security Policy and budget gate
  - Generate the CSP headers file for the host; the budget check becomes a failure once engine sharding exists.
  - _Requirements: REQ-WEB-PERF.1, .3_
- [x] 13. [credibility] Sensitivity tier toggle
  - Outline markers, tier notes on cards, headline count always shown first.
  - [x] 13.1 Property W6: headline mode never contains non-headline zombies; the headline count is unchanged when the toggle is on. _REQ-WEB-TIER.1–2_
  - _Requirements: REQ-WEB-TIER.1–2_
- [x] 14. [credibility] Survival and funnel charts, leaderboards
  - Plain SVG components; intervals always visible; "unusual" only outside 99.8%; reporting intensity beside every neighborhood rate.
  - _Requirements: REQ-WEB-CHARTS.1–2_
- [x] 15. [credibility] Methods page, status and corrections
  - Definitions, baselines, excess with the shift distribution, placebo, validation precision and kappa, limitations; Methods introduction as TODO-COPY; nightly status and `calibration_warning`; "Report an error" link; corrections page from `docs/CORRECTIONS.md`.
  - _Requirements: REQ-WEB-METHODS.1, REQ-WEB-FRESH.2–3_
- [x] 16. [credibility] What the headline leaves out
  - Separate deaths, temporary-fix return rates, exclusions, the `source_unknown` explanation, the bulk-closure layer in Cone orange.
  - _Requirements: REQ-WEB-DEATHS.1_

## Delight

- [x] 17. [delight] Sensitivity sliders
  - _Requirements: REQ-WEB-SLIDERS.1_
- [x] 18. [delight] "Check my street"
  - Build-time address index from the SAM address registry; search, zoom, nearby list, empty state.
  - _Requirements: REQ-WEB-STREET.1_
- [x] 19. [delight] Repeat offenders view
  - _Requirements: REQ-WEB-REPEAT.1_
- [x] 20. [delight] Permalinks and share images
  - [x] 20.1 Property W7: URL state round-trips. _REQ-WEB-LINKS.1_
  - _Requirements: REQ-WEB-LINKS.1–2_
- [ ] 21. [delight] Night of the Living 311 time-lapse
  - _Requirements: REQ-WEB-TIMELAPSE.1_
- [ ] 22. [delight] Spanish evidence cards
  - `es.json` drafts marked `needs-review`, hidden in production until reviewed.
  - _Requirements: REQ-WEB-ES.1_
- [ ] 23. [delight] Open data download, district report cards, before/after display
  - _Requirements: REQ-WEB-OPEN.1–3_
