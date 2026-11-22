# Design review, 2026-11-22

Scope: suggestions only. The review covers eight pages at 1280 px and 390 px wide, against `design-system.md` and `voice.md`. Screenshots are in `docs/design-review/shots/` (named `desktop-<page>.png` and `phone-<page>.png`). They come from the production build with the snap-1120 exports (data version `2026-11-20+27ceb33+89e078da`, release asset `exports-snap-1120`, SHA-256 checked) and the judge-mode files from `data/judging/`. No data or judge-mode file is changed by this work.

Two readers: the `reviewer-ux` agent (its findings are in `.local-data/review-ux.json`, not committed) and the author. The agent worked from the screenshots only and marked what it could not check. The author checked the same pages in the browser and measured page heights.

## What the review found

**Where the idea comes through.** The home map is the strongest page: spray-blob clusters with count tags are specific to this project. The autopsy card works too (struck CLOSED stamp, tilted pink REPORTED AGAIN stamp, canary Courier fields, single copy on phones). The time-lapse date plaque is the one other place with character.

**Where it is missing.** Every other page is a grey page with a heading and bordered white boxes. Scorecard, durability, methods, street and judge have no paint, no pink and no form structure. Cone orange and Canary appear only on the card and the methods warning. On the card, the triplicate offset is two slivers at the right edge and reads as a rendering glitch.

**Generic dashboard test.** With the name removed, the home map and the card are still recognizable. The other six pages are not.

**Banned defaults.** None found: no gradients, no neon on black, no tracked caps eyebrows, no emoji icons. The nearest miss is one box style (2 px Asphalt border, off-white fill) used for filters, scorecard rows, notices, buttons and chart frames, so nothing separates a control from content from a warning.

**Voice.** No banned words or exclamation marks. One notice on `/judge` ends without a full stop.

**Numbers.** Counts had no thousands separators (`19077`, `n = 309590`). Fixed in this PR.

**Page lengths on the snap-1120 data** (document height at 1280 px): `/street` after picking Dorchester Ave 19,997 px (474 results in one list); `/repeat` 36,535 px (547 rows in one table); `/durability` 3,982 px; `/scorecard` 2,087 px. On a phone `/repeat` is 64,414 px and `/street` 28,244 px.

## Suggestions, ranked by impact over effort

Effort: S is under half a day, M is one to two days, L is more than two days. "Built" means it is in the draft PR `design/proposals`.

| # | Suggestion | Impact | Effort | Status |
|---|---|---|---|---|
| 1 | Thousands separators on every count | High | S | Built |
| 2 | Compact credits strip | High | S | Built (CSS part) |
| 3 | Tour link becomes the one action in the header | Medium | S | Built |
| 4 | Basemap hierarchy so pink reads first | Medium | S | Built (modest) |
| 5 | Lead the sidebar with the count, drop the duplicate title | High | S | Mock A |
| 6 | Cap the street and repeat lists | High | M | Proposed |
| 7 | Scorecard draws the gap | High | M | Proposed |
| 8 | Durability: remove columns that carry nothing | Medium | S | Proposed |
| 9 | Street page empty state with examples | Medium | M | Proposed |
| 10 | Give controls, content, notices and warnings different looks | Medium | S | Proposed |
| 11 | Stronger type scale and tabular figures | Medium | S | Proposed |
| 12 | Make the triplicate form read as three copies | Medium | M | Proposed |
| 13 | Judge intro page shows what the tour is | Medium | M | Proposed |
| 14 | Time-lapse final frame and reduced-motion banner | Medium | M | Proposed |
| 15 | Phone first screen: header, count strip and footer | High | M | Proposed |

### 1. Thousands separators on every count (S, built)

Now: `19077 possible zombies` in the sidebar (`shots/desktop-home.png`), `n = 309590` on the scorecard (`shots/desktop-scorecard.png`), `Counts: 19077 headline, 98 source unknown`. Long digit runs are hard to read and look unfinished beside the typeset percentages.
Change: `t()` in `web/src/lib/t.ts` formats integer parameters named `count`, `n`, `total`, `k`, `below`, `covers`, `bursty`, `observed`, `headline`, `all`, `source_unknown` and `sensitivity` with `Intl.NumberFormat("en-US")`. Years and ids are untouched. Two tests that pinned the unformatted text were updated. Result: `after/after-desktop-home.png`, `after/after-desktop-scorecard.png`. Spanish still uses the English separators; a `es` locale format is a follow-up for the native-speaker review.

### 2. Compact credits strip (S, built; M for the full version)

Now: the credits are five stacked lines on every page except the map. On the scorecard they are a ragged block with a stray centred line (`shots/desktop-scorecard.png`, bottom). On a phone the open bar covers about a quarter of the first screen (`shots/phone-home.png`).
Built: the run-in layout the map page already used now applies to every page (CSS only, text and the close button unchanged). The bar is three lines on a wide screen instead of five (`after/after-desktop-scorecard.png`).
Next step: one line, "Independent project. Not affiliated with the City of Boston." plus a "Credits and licenses" disclosure, as in the mocks. That changes the markup and the footer tests, so it is not in this PR. Keep the OpenStreetMap credit on the map itself.

### 3. Tour link as the one action in the header (S, built)

Now: eight underlined links in one row, and the tour link looks like a page (`shots/desktop-home.png`, top). The active page differs from the others only by weight.
Built: on screens wider than 640 px "Start the 60-second tour" is a boxed link at the right end of the nav (`after/after-desktop-home.png`). It fills with Crew white when it is the current page. The phone menu stays a plain list. All header links are still 44 px tall (the existing test passes).
Next step: group the nav into primary (Map, Check my street, Repeat offenders) and secondary links. Put "Data as of" on the same row when it fits.

### 4. Basemap hierarchy (S, built, modest effect)

Now: every road is solid Asphalt, so the map is a uniform dense grey drawing and the pink marks compete with it (`shots/desktop-home.png`).
Built in `web/src/map/style.ts`: small streets start at zoom 12.5 instead of 11 and draw at 60 percent opacity; medium roads at 50 percent; water edges at 70 percent. Arterials and highways stay full Asphalt. No new color is added. The change is visible but small at the opening zoom (`after/after-desktop-home.png`); checked by eye only.
Next step (M): fill water lighter than land, and set five hand-placed labels (Downtown, Dorchester, Roxbury, Charlestown, Jamaica Plain). The style has no glyphs yet, so labels need a self-hosted font stack.

### 5. Lead the sidebar with the count (S)

Now: the sidebar repeats the site name as an `h1` right under the header, then two paragraphs, then the count in body size (`shots/desktop-home.png`). The number that tells the story is the third thing read.
Change: drop the duplicate title (keep one `h1` for screen readers), set the count at about 3.2 rem in Public Sans 800, and put a short dashed divider with a pink segment under it, like a crew's line mark. Mock A shows it (`directions/a-home-desktop.png`). Copy stays as is; any new sentence is `TODO-COPY`.

### 6. Cap the street and repeat lists (M)

Now: after picking Dorchester Ave the street page is 19,997 px tall with 474 results (`shots/desktop-street-result.png` shows only the first screen), and the map shows the whole city, not the street. `/repeat` is 36,535 px with 547 rows (`shots/desktop-repeat.png`); the table starts below the fold.
Change: show the first 20 results with "Show 20 more" (keep the full list reachable by keyboard and in the DOM only as it is revealed). Fit the street map to the 150 m circle. On `/repeat`, put the table's top 20 beside the map and link them: hover on a row rings the cluster. This also helps the first-view budget and phone scroll length (64,414 px on `/repeat`).

### 7. Scorecard draws the gap (M)

Now: nine identical boxes (`shots/desktop-scorecard.png`). The story is the gap between "closed on time" and "stayed fixed", but it is two numbers apart. Traffic signals (95.3 percent on time, 78.2 percent stayed fixed) look like street fixtures (99.4 and 97.7). The interval marks are 3 px wide because the intervals are narrow. The right quarter of the page is empty, and the upper-bound note sits under the last box in small text.
Change: one table-like form, rows sorted by gap. Each row has one 0 to 100 scale with a hollow Asphalt circle (on time) and a pink spray circle (stayed fixed) joined by a line, with the gap in points as a number. Keep both rates and intervals as numbers. Move the upper-bound note under the title. The pink mark carries meaning here (possible zombies), so it follows the palette rule.

### 8. Durability: remove columns that carry nothing (S)

Now: the half-life column says "Above 50% through day 90" in all eight rows. The reporting-intensity column says "Not available in this data" on every group row. Groups with 1 to 12 cases ("(unknown)", "ECON (as published)", "BPS") sit in the same table as a department with 196,462 cases. The funnel limits draw as jagged, overlapping lines (`shots/desktop-durability.png`).
Change: hide the half-life column while it is the same for every row, with one sentence under the table. Remove the reporting-intensity column until it has data. Fold groups with fewer than 30 cases behind "Show small groups". Plot the funnel limits on a fixed grid of n so the lines are smooth. Voice: "Stayed fixed (raw)" and "Against chance" need a plain-words note.

### 9. Street page empty state (M)

Now: one input on a blank grey page (`shots/desktop-street-empty.png`).
Change: show the city map with the clusters behind the form, and three example streets from the data as buttons that run the search. The input stays the first control. Example street names come from the data; the empty-state sentence is human-written (`TODO-COPY`). Darken the placeholder or drop it, since the label already exists (contrast is unverified).

### 10. Different looks for controls, content, notices and warnings (S)

Now: one box style everywhere. Cone orange appears on no page in the screenshots.
Change: controls stay Concrete with a 2 px Asphalt border. Content panels are Crew white with a thicker top edge. Notices keep the dashed border and no fill. Warnings (bulk closures, calibration) get the orange left bar already defined, and nothing else is orange. One primary button style per page (Asphalt fill) and secondary buttons as now.

### 11. Stronger type scale and tabular figures (S)

Now: page title, card title and body are within about 8 px of each other, so nothing leads (`shots/desktop-methods.png`, `shots/desktop-judge-intro.png`).
Change: page title about 2.25 rem at weight 800, section title 1.4 rem, body 1.05 rem, small 0.875 rem, `font-variant-numeric: tabular-nums` on every figure. Courier Prime stays inside forms only. Cap `/methods` and `/judge` at 68 characters.

### 12. Make the triplicate form read as three copies (M)

Now: on desktop the canary and pink copies show as two thin slivers (`shots/desktop-card.png`). The form has no header row.
Change: offset the copies 10 px, add a form header row in Courier (form name, case number from the data), and let the top copy slide 8 px aside once when the card opens (the one allowed interaction motion, off under reduced motion). Ring the selected marker on the map so the card does not hide which one it is. On phones keep the single copy.

### 13. Judge intro page shows what the tour is (M)

Now: a notice, three lines, two buttons and 400 px of empty grey (`shots/desktop-judge-intro.png`). The notice ends without a full stop.
Change: show the three zombies as small stamped cards (map crop and case type) so the page promises something. Move key hints into a "Keys" disclosure. Fix the punctuation. Note: `data/judging` on `main` is the provisional stage; the record-confirmed tour is on `feat/judging-final-exports-only`. The notice wording depends on which one is deployed, so the copy stays a human decision.

### 14. Time-lapse final frame and banner (M)

Now: with reduced motion on, the static end state is a dark magenta mass over the city (`shots/desktop-timelapse.png`). Markers merge and lose the spray look, and the reduced-motion banner is the first sentence read. The animation itself was not reviewed (the stills used reduced motion).
Change: draw older years at lower opacity so the newest year stays vivid, and show the reduced-motion note as a small caption with a year scrubber below. Reword "Focus the view" to say what it does.

### 15. Phone first screen (M)

Now: the header is 108 px, the count strip about 60 px, the Map and Table row 44 px, and the open footer covers the lower part of the map (`shots/phone-home.png`).
Change: collapse the footer to the one-line strip from suggestion 2 by default on phones, merge the count and "Show filters" into one row, and move "Data as of" into the menu sheet with a short caption at the map's edge. A header row with the title, the date and the Menu button does not fit at 390 px (about 380 px of content in 358 px), so the date has to move. Target: map is at least 65 percent of the first screen.

Also noted, not ranked: the table view's "Time in the grave" and "Confidence" cells were empty in `shots/desktop-home-table.png` (taken 0.8 s after switching; likely shards still loading, not checked further). Row links read "Open card 101003380449:101006546009", which is an id, not words.

## Three directions

Each mock is the home page at 1280 px on snap-1120, drawn by injecting CSS into the built page. None of it is in the app. The three share the compact credits strip from suggestion 2.

### A. Refine the civic field-survey look

`directions/a-home-desktop.png`. The count leads the sidebar at display size, the duplicate title is gone, a dashed divider with a short pink segment separates the count from the filters, the active nav item gets an underbar, and the tour is a boxed action. Palette, type and layout stay as the design system defines them. Cost: S to M, mostly CSS and one markup change. Risk: low. It makes the page calmer but does not add new personality.

### B. A bolder version

`directions/b-home-desktop.png`. The sidebar becomes a canary form: Courier throughout, the count in a hard-bordered box with a pink offset copy and a tilted REPORTED AGAIN stamp, a thick pink survey line under the header, and a framed map. This leans into the "typed municipal form" idea. Costs and risks: Courier outside the autopsy form breaks the type rule in `design-system.md` ("only inside the autopsy forms"), so the rule would need an owner decision. The pink bar under the header is graphic, not text, but "never decorative" needs the same decision. The stamp is clipped by the sidebar in this mock; it would need room. Cost: M to L.

### C. The same look with a Kiroween touch

`directions/c-home-desktop.png`. Paperwork humor only: a "Night shift" stamp beside the title, a "Filed after dark" stamp on the map, and the count in a toe-tag shape with a punched hole. No bones, slime or horror type, and nothing changes in the data views. Apply it to the home page, the card and the time-lapse; the evidence pages stay plain. Cost: S to M. Risk: the stamps are decoration, so they must be easy to hide and must never cover a marker; the tag shape clips the count box and needs a check at 390 px. Remove it after the Jan 29 judging window if it reads as a costume.

Recommendation: A first (it fixes the page's actual problems), then C as a layer for the submission window. B needs the rule changes above.

## What is in the draft PR

Branch `design/proposals`, suggestions 1 to 4:

- `web/src/lib/t.ts`: thousands separators for count parameters.
- `web/src/map/style.ts`: road and water opacity, minor roads from zoom 12.5.
- `web/src/styles/app.css`: run-in credits on every page; boxed tour link.
- `web/src/components/Scorecard.test.tsx`, `web/src/components/Sliders.test.tsx`: expected text now has separators.
- `docs/DESIGN_REVIEW.md` and `docs/design-review/` (screenshots, after shots, direction mocks).

No file under `web/public/data/` or `data/` is changed.

## Checks

On the sample data the repo commits: `tsc --noEmit` clean; `vitest` 532 of 532 pass; Playwright `a11y.spec.ts`, `footer.spec.ts` and `ui-polish.spec.ts` on desktop and phone, 80 passed and 4 skipped (the axe scans are in `a11y.spec.ts`). The production build reports a first view of about 1.9 MB against the 3 MB budget (with the snap-1120 data). The full `make test` and `ruff` were not run; only the web side changed.

## Limits of this review

- The Netlify deploy preview builds from the data committed in the repo (the sample export), not snap-1120, because the data files must not change in this PR. Numbers on the preview differ from the screenshots; the layout is the same.
- Screenshots use reduced motion, so the time-lapse animation and the card's motion were not reviewed.
- Keyboard focus rings, placeholder contrast and the phone views of `/scorecard`, `/durability`, `/methods`, `/repeat` and `/street` were not checked by the agent. The author took the phone shots but looked at them only for the home page, the card, the time-lapse and the judge page.
- The footer and header changes were measured against the existing tests, not against a new visual diff.
