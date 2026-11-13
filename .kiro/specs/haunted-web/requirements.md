# Requirements: haunted-web

## Introduction
The haunted web app is a static Vite + React + TypeScript site. It shows possible zombies on a map of Boston, an autopsy card for each, the two-number scorecard, the statistics, and a 60-second judge-mode tour. It reads only the static files the pipeline writes to `web/public/data/` and makes no runtime requests to third parties. Visual design follows `.kiro/steering/design-system.md`, and words follow `voice.md` and `language.md`. Interface text a person must write is a `TODO-COPY: <what it must say>` placeholder in `web/src/copy/en.json`.

IDs use the prefix `REQ-WEB-`. Layers follow docs/PROJECT.md: **demo-critical** (by Nov 17), **credibility** (by Nov 22), **delight**. Acceptance criteria are in EARS form.

---

### REQ-WEB-DATA: Data loading and contracts
**Layer:** demo-critical
**User story:** As the app, I want to parse only valid data, so a bad file can't break the site silently.
1. THE app SHALL load data only from same-origin static files, and parse each file with a parser that matches the JSON Schemas in `/schemas/` (types generated from the schemas).
2. IF a file fails parsing, THEN THE app SHALL show the error state from `en.json` for that panel and keep the rest of the page working.
3. WHILE the engine's real exports don't exist, THE app SHALL use fixture files generated from `data/sample/` that follow the same schemas.

### REQ-WEB-MAP: Haunted map with filters
**Layer:** demo-critical
**User story:** As a resident, I want to see where problems came back and filter them, so I can find my area and the services I care about.
1. THE app SHALL open on a map of Boston with possible zombies drawn as survey-pink spray-circle markers from a 3–5 variant sprite atlas (deck.gl IconLayer), over a self-hosted Boston PMTiles basemap restyled to the palette.
2. THE app SHALL filter by neighborhood, department, family (case type) and year, and SHALL show the count of possible zombies matching the filters.
3. WHEN filters change, THE app SHALL update the map, the count and the table view (REQ-WEB-TABLE) to the same set of zombies.
4. THE app SHALL show headline-tier zombies by default (REQ-WEB-TIER).
5. THE app SHALL always show OpenStreetMap attribution.

### REQ-WEB-CARD: Autopsy cards
**Layer:** demo-critical
**User story:** As a reader, I want the evidence for one zombie on one form, so I can judge it myself.
1. WHEN a zombie is selected (map, table or tour), THE app SHALL show its autopsy card with: Cause of death (closure label), Time in the grave (gap days), Resurrection date, Confidence (with `partial` shown when `confidence_partial`), Skeptic's objections and verdict, and both case records (original and re-report: IDs linking to the city's public case pages, dates, type, scrubbed closure text).
2. THE card SHALL look like a triplicate city form (Crew white, Canary, pink copies offset, a struck "CLOSED" stamp re-stamped "REPORTED AGAIN"), using the typewriter face only inside the form.
3. THE card SHALL say "possible zombie" and never claim intent or name any worker.
4. THE app SHALL load card shards lazily, only when needed.
5. WHEN the viewport is phone-sized (under 640 px wide), THE card SHALL collapse to one readable copy in a bottom sheet.
6. WHEN the incident's closure is part of a bulk closure, THE card SHALL show a Cone orange warning (with an Asphalt text label, never orange text).

### REQ-WEB-SCORE: Two-number scorecard
**Layer:** demo-critical
**User story:** As a councilor, I want "closed on time" next to "stayed fixed" for each category, so I see speed and durability together.
1. THE app SHALL show, per family and citywide, the on-time rate and the stayed-fixed rate side by side, each with its 95% interval and n.
2. WHEN the adjusted stayed-fixed rate exists, THE app SHALL show it as the stayed-fixed number and offer the raw rate in a detail view. The label SHALL say which one is shown.

### REQ-WEB-JUDGE: Judge mode
**Layer:** demo-critical
**User story:** As a judge, I want a 60-second guided tour with no login, so I understand the project fast on any device.
1. THE app SHALL offer judge mode from the first screen. It plays a tour of three zombies from `judge_tour.json` on the frozen judging snapshot: about 60 seconds, skippable and pausable, keyboard operable, with reduced-motion support.
2. WHEN the app is built as the judging build (`make build JUDGING=1`, used from the snapshot freeze onward), THE build SHALL fail if `judge_tour.json` is provisional or any tour zombie is not in the confirmed validation set (REQ-STAT-TOUR, REQ-STAT-VAL.3).
3. WHILE `judge_tour.json` is provisional (before field validation), every other build (dev, preview, the pre-freeze production deploy used for storyboarding) SHALL play the provisional tour and show a visible "provisional tour" notice from `en.json`.
4. THE tour SHALL work on a phone-sized viewport within the first-view payload budget (REQ-WEB-PERF).

### REQ-WEB-TABLE: Table view mirrors the map
**Layer:** demo-critical (design-system.md quality floor)
**User story:** As a keyboard or screen-reader user, I want the map's contents as a sortable table, so I never need the map to get the facts.
1. THE app SHALL offer a table view with the same zombies as the map under the current filters, sortable by date, gap, neighborhood, family and confidence. Each row opens the same autopsy card.

### REQ-WEB-A11Y: Accessibility floor
**Layer:** demo-critical
1. THE app SHALL be keyboard-navigable with visible focus, meet WCAG AA contrast (never pink or orange text on Concrete), avoid relying on color alone (shape and table also mark zombies), and respect `prefers-reduced-motion` for every animation.
2. THE app SHALL pass an automated axe scan of judge mode with no serious or critical violations. In the demo-critical layer it runs locally in `make e2e`; CI enforces it from the credibility layer (REQ-OPS-CI.2).

### REQ-WEB-COPY: Copy in one place
**Layer:** demo-critical
1. THE app SHALL take all interface text from `web/src/copy/en.json` (and `es.json` when present). Components contain no hard-coded user-facing strings.
2. THE human-written items in voice.md (hero line and subtitle, About, Methods introduction, error and empty-state voice samples) SHALL be `TODO-COPY:` placeholders until a person writes them.
3. THE app SHALL follow voice.md for every string an agent writes (sentence case, buttons say what happens, no banned words). `make copy-lint` SHALL report 0 banned items.

### REQ-WEB-DESIGN: Design-system compliance
**Layer:** demo-critical
1. THE app SHALL use only the six palette colors with their meanings, Public Sans (self-hosted), one type scale, and the layout rules in design-system.md (the map is the hero: no marketing hero, stat banner or feature cards).
2. THE app SHALL contain none of the items in design-system.md "Banned defaults" (verified by `make copy-lint` for CSS patterns and by the reviewer-ux checklist for the rest).
3. THE app SHALL show the footer "Independent project. Not affiliated with the City of Boston." with OpenStreetMap credit and data licenses on every page. It SHALL use no city seal or third-party logos.

### REQ-WEB-FRESH: Data freshness and corrections
**Layer:** demo-critical ("Data as of"); credibility (status and corrections)
1. THE app SHALL show "Data as of <date>" from `status.json` on every page.
2. THE app SHALL show the nightly status (last run, anomalies, `calibration_warning`) on the methods page, and keep showing the last good data if the latest run failed.
3. THE app SHALL offer a "Report an error" link on every card and a public corrections log page rendered from `docs/CORRECTIONS.md` at build time.

### REQ-WEB-PERF: Performance and security
**Layer:** demo-critical (budget, no third-party requests); credibility (CSP header, bundle budget in CI)
1. THE first view (map plus judge mode entry) SHALL load under 3 MB of transferred data. The build measures it: a warning in the demo-critical layer, and a build failure once the engine's sharding (REQ-EXP-SIZE, credibility) exists.
2. THE app SHALL make no runtime requests to any origin other than its own (fonts, basemap tiles and data are self-hosted).
3. THE app SHALL ship a Content Security Policy that allows only same-origin scripts, styles, images, fonts and connections.

### REQ-WEB-TIER: Sensitivity toggle
**Layer:** credibility
**User story:** As a careful reader, I want to include the sensitivity tier on demand, so I can see what the headline leaves out.
1. THE app SHALL offer a toggle that adds `source_unknown` and `sensitivity` zombies to the map, table and counts. Those markers are visually distinct (outline only) and labeled on their cards.
2. WHEN the toggle is on, THE app SHALL show both the headline count and the all-tier count, never the all-tier count alone.

### REQ-WEB-CHARTS: Survival and funnel charts, leaderboards
**Layer:** credibility
1. THE app SHALL show Kaplan–Meier survival curves with intervals by department and family, with the 7/30/90-day shares and half-life.
2. THE app SHALL show funnel plots (rate against n, 95% and 99.8% limits) and leaderboards of shrunk rates with intervals and reporting intensity. Only groups outside the 99.8% limits are called "unusual". Raw rankings never appear alone.

### REQ-WEB-METHODS: Methods page
**Layer:** credibility
1. THE app SHALL have a methods page with the definitions (from zombie-definition.md), the baselines, the excess with the shift-test distribution, the placebo result, validation precision with its interval and kappa, limitations ("counts are a floor"), and the Methods introduction as a TODO-COPY placeholder.

### REQ-WEB-DEATHS: What the headline leaves out
**Layer:** credibility
**User story:** As a careful reader, I want to see everything the headline doesn't count, so nothing is hidden.
1. THE methods page SHALL show the separate deaths (`invalid`, `duplicate`), how often temporary fixes come back (REQ-STAT-TEMP), the exclusion counts by reason, what `source_unknown` means and why it is outside the headline, and the bulk-closure days (Cone orange markers on an optional map layer).

### REQ-WEB-SLIDERS: Sensitivity sliders
**Layer:** delight
1. THE methods page SHALL offer controls for matching mode, RADIUS_M and WINDOW_DAYS that switch instantly between precomputed grid points (`sensitivity_grid.json`), plus the run without Street Light Other.

### REQ-WEB-STREET: "Check my street"
**Layer:** delight
1. THE app SHALL search a compact client-side index built from the SAM address registry at build time (no API). It SHALL zoom to the street and list nearby possible zombies, with an empty state that suggests widening the window.

### REQ-WEB-REPEAT: Repeat offenders view
**Layer:** delight
1. THE app SHALL list chains with `times_risen >= 3`, shown at the location the engine exports (block level for residential chains driven by resident reports, REQ-EXP-PRIV).

### REQ-WEB-LINKS: Permalinks and share images
**Layer:** delight
1. THE app SHALL give every zombie, neighborhood and filter state a permalink (URL state).
2. THE build SHALL render a share image per zombie and per neighborhood (static files, no runtime service).

### REQ-WEB-TIMELAPSE: Night of the Living 311
**Layer:** delight
1. THE app SHALL play a time-lapse of possible zombies appearing across Boston, 2015 to the snapshot. It is the single orchestrated animation: skippable, and replaced by a static summary under reduced motion.

### REQ-WEB-ES: Spanish evidence cards
**Layer:** delight
1. THE app SHALL offer Spanish for autopsy cards and the scorecard from `es.json`. Strings drafted by an agent SHALL be marked `needs-review` until a native speaker reviews them, and are hidden in production until then.

### REQ-WEB-OPEN: Open data and report cards
**Layer:** delight
**User story:** As a journalist or neighborhood group, I want the data and a printable page per district, so I can use the findings myself.
1. THE app SHALL link a download of the zombie dataset (CSV and JSON, with its license) from the methods page.
2. THE app SHALL offer one printable report card per council district (print stylesheet), with the district's scorecard, intervals and reporting intensity.
3. WHEN the before/after system-change comparison exists (REQ-STAT-CREATIO), THE methods page SHALL show it with its artifact warning.

### REQ-WEB-TEST: Tests
**Layer:** demo-critical
1. WHEN `make test` runs, THE web test suite SHALL run vitest unit tests and the fast-check properties W1–W8 (design), and SHALL fail on any failure.
2. WHEN `make e2e` runs, THE Playwright test SHALL drive the judge-mode path on phone and desktop viewports, keyboard only, with reduced motion on and off, and SHALL fail if any step is missing.
