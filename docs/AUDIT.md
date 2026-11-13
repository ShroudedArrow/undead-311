# The Undead 311: refinement audit

*A line-by-line review of the project from 14 angles, run before the one-shot build (Oct 31, 2026). Covers the project write-up, Kiro playbook, pre-flight checklist, starter kit, and the official rules.*

**How to read this**
- **Priority:**
  - **P0:** before launching the build.
  - **P1:** during weeks 1–3.
  - **P2:** only if time allows.
- **Status:**
  - **Applied:** already changed in the starter kit and/or the published write-up.
  - **To do:** a team action, with the owning role (Data, Kiro, or Story lead).

---

## The 12 highest-leverage changes

| # | Change | Why it matters | Status |
|---|---|---|---|
| 1 | **Incidents before matching:** group duplicate reports into one incident first | Without this, one pothole reported three times can count as several zombies | Applied |
| 2 | **Planned follow-ups aren’t zombies** | City crews often make a spot safe, then come back for the permanent repair. City-generated follow-up cases would otherwise look like failed fixes | Applied |
| 3 | **Handle the 2025 system change** (new system from August 2025, type by type) | Field names changed. Without a crosswalk, a closure in the old system can’t match a re-report in the new one | Applied |
| 4 | **Street-segment matching is now a must-have** | Boston’s street-segment data is public domain and updated nightly; it beats a raw radius at intersections and on parallel streets | Applied |
| 5 | **“Check my street” search** | The most natural first action for residents and judges (“Would someone actually use this?”) | Applied |
| 6 | **Zombie chains and “repeat offenders”** | “This sidewalk died and rose four times” is the most memorable finding the data can produce | Applied |
| 7 | **Counts are a floor (reporting bias)** | Zombies only appear where someone re-reports. Saying so prevents unfair neighborhood comparisons and builds trust | Applied |
| 8 | **Fixed a wrong property test** | “A bigger radius never finds fewer zombies” breaks once incidents merge. It’s now stated on candidate pairs | Applied |
| 9 | **“Test town” golden fixture** | A hand-built case set with known answers gives the one-shot build a correctness anchor | Applied |
| 10 | **Two blind raters for validation** | Reporting agreement between raters makes the precision number defensible | Applied |
| 11 | **Acknowledge the Boston Globe pothole tracker** | Judges may know it. It shows volume; we show durability | Applied |
| 12 | **Kiro experiments log** | The rubric asks “Was there experimentation?” Four small controlled comparisons answer it with evidence | Applied (template); To do (Kiro) |

---

## A. Story and positioning

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| A1 | Our speed-vs-durability framing cites older CityScore targets, and CityScore® is a registered trademark | Describe CityScore only descriptively; confirm current targets in its dataset; compute on-time rates from the 311 data itself | P0 | Applied |
| A2 | The Boston Globe already maps open and closed pothole requests | Name it in prior art; position as durability, not volume | P0 | Applied |
| A3 | Zombie counts depend on someone re-reporting | Say “counts are a floor” everywhere | P0 | Applied |
| A4 | The pitch line isn’t final | A teammate writes it (12 words max) and tests it on 3 people outside the team | P1 | To do (Story) |
| A5 | Different surfaces could lead with different numbers | Lead the site, video, and Devpost page with the same two numbers: closed on time vs. stayed fixed | P1 | To do (Story) |
| A6 | Metric naming must stay consistent | Confirm “stayed-fixed rate” as the name and use it everywhere | P0 | To do (team) |

## B. Rules and judging fit

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| B1 | Judging may use AI-driven analysis and may skip testing the app | Fill in `CRITERIA_MAP.md`; put evidence where a reader (or a model) finds it first | P1 | To do (Kiro) |
| B2 | Stage 1 is pass/fail on theme and Kiro use | Make both obvious in the first 10 seconds of the video and the first screen of the README | P1 | To do (Story) |
| B3 | Frankenstein fit must be argued, not assumed | List the stitched parts: two city CRM data formats + the street-address registry + reliability statistics + AI coroner and skeptic agents + scheduled Crew agents + Discord + hand-made spray-paint assets | P1 | To do (Story) |
| B4 | Post-deadline repo changes are risky | Tag the submission; nightly refresh lives in a separate data repo | P0 | Applied |
| B5 | The Kiro write-up must answer 8 specific questions | Evidence matrix plus `EXPERIMENTS.md` | P1 | Applied (template) |

## C. Data

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| C1 | Boston moved 311 to a new system from August 2025 (most in-scope types by mid-2026), with different field names, across three resource groups | Schema adapter, type crosswalk, cross-system matching; a test-town case spans the switch | P0 | Applied |
| C2 | The source field includes city-originated channels (Employee Generated, City Worker App, Maximo Integration) | Planned-follow-up rule; show results with and without them | P0 | Applied |
| C3 | Placeholder coordinates exist (City Hall shows up as a default) | Detect high-frequency default points automatically; count exclusions | P0 | Applied |
| C4 | The dataset ships a CRM Value Codex | Use it to interpret codes | P0 | Applied |
| C5 | SAM street segments and SAM addresses are public domain, updated nightly | Segment matching (must-have); client-side address search | P0 | Applied |
| C6 | About 270,000 rows and 125 MB per year (2021) | DuckDB handles ~3M rows easily. Benchmark the full nightly run (target under 20 min) | P1 | To do (Data) |
| C7 | A case reopened under the *same* ID is a direct resurrection signal, but snapshots hide it | From nightly snapshots, record closed → open status changes going forward | P2 | To do (Data) |
| C8 | NOAA’s API may need a token | Confirm in week 1, or use bulk daily files | P1 | To do (Data) |
| C9 | Reporting-intensity context needs a denominator | Use street-km from SAM segments (no extra data); add population later if needed | P1 | Applied (method) |

## D. Methods

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| D1 | Duplicate reports would double-count | Incidents first (partition property test) | P0 | Applied |
| D2 | “Earliest vs. most recent” attribution was ambiguous | Process re-reports in time order; attach each to the most recent eligible incident; break ties by ID | P0 | Applied |
| D3 | Repeated failures weren’t captured | Chains, `times_risen`, repeat offenders | P0 | Applied |
| D4 | Planned two-stage repairs look like zombies | Planned-follow-up rule plus new Coroner labels (made safe, planned follow-up) | P0 | Applied |
| D5 | The monotonic-count property was false | Restated on candidate pairs | P0 | Applied |
| D6 | Neighborhoods that report less show fewer zombies | Show reporting intensity; call rates a floor | P0 | Applied |
| D7 | Is the baseline calibrated? | Placebo run on time-shifted closures; excess should be near zero | P1 | Applied (method) |
| D8 | Single-month trends exaggerate | Rolling multi-month windows; “unusual” only beyond 99.8% funnel limits | P1 | Applied |
| D9 | Validation could be accused of bias | Seeded sample committed before visits; two blind raters; Cohen’s kappa; visit dates recorded | P0 | Applied |
| D10 | We only measure precision, not misses | Optional: check a small random sample of unflagged closures | P2 | To do (Data) |
| D11 | Rates without counts mislead | Show denominators everywhere (“12 of 340”) | P1 | To do (Story) |
| D12 | The confidence score must mean something | Check it against validation labels: do higher scores really hold up more often? | P1 | To do (Data) |

## E. Product and UX

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| E1 | No obvious first action for a resident | “Check my street” search | P0 | Applied |
| E2 | Features weren’t tied to real journeys | Write 3 journeys (resident, journalist, councilor’s staffer) as end-to-end tests | P1 | To do (Story + Kiro) |
| E3 | Mobile layout unspecified | Map plus a bottom sheet for evidence cards | P1 | To do (Story) |
| E4 | Sensitivity was a static table | Interactive sliders over the precomputed grid | P1 | Applied (should-have) |
| E5 | Repeat failures had no home | Repeat-offenders view | P0 | Applied |
| E6 | Little to share | Share images per zombie and neighborhood | P1 | Applied (should-have) |
| E7 | Users can’t act on a zombie | “Report it again” link to official 311 channels | P1 | To do (Kiro) |
| E8 | Freshness and errors unclear | “Data as of,” nightly status, report-an-error link, public corrections log | P0 | Applied |
| E9 | Report cards need to print | Print stylesheet for district report cards | P1 | Applied (should-have) |
| E10 | Machine-only translation reads as AI | Spanish reviewed by a native speaker | P1 | Applied |
| E11 | First visit has no guidance | A dismissible “start here” hint plus judge mode | P1 | To do (Story) |

## F. Design

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| F1 | “Dark map with zombies” was a generic default | Concrete and asphalt palette with spray-paint pink | P0 | Applied |
| F2 | Pink and orange fail contrast as text | Never used for text; marker outlines; shape plus color | P0 | Applied |
| F3 | The signature assets need to exist | Spray-paint session in week 1; scan and vectorize | P1 | To do (Story) |
| F4 | Agents may drift from the design | Generate CSS variables (design tokens) from `design-system.md` so every component uses them | P1 | To do (Kiro) |
| F5 | The map style isn’t designed yet | Tune label density, harbor and park colors, and street weights by hand | P1 | To do (Story) |
| F6 | Brand pieces scattered | One favicon, share image, and Devpost thumbnail system | P1 | To do (Story) |

## G. Engineering

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| G1 | The pipeline and web app could drift | JSON Schemas in `/schemas/`; contract property test | P0 | Applied |
| G2 | Non-deterministic outputs make diffs noisy | Stable IDs, sorted output, a `data_version` stamp | P0 | Applied |
| G3 | Nightly failures could break the site | `status.json`, alerts, last-good fallback | P0 | Applied |
| G4 | Large payloads | Under 3 MB first view; sharding; lazy-loaded cards | P1 | Applied |
| G5 | Supply-chain and script risk | CSP, no runtime third-party scripts, audits in CI, pinned actions | P1 | Applied |
| G6 | One-shot correctness needs an anchor | “Test town” golden fixture with exact expected output | P0 | Applied |
| G7 | Hidden invariants | Metamorphic tests (translation, time shift, duplication) | P0 | Applied |
| G8 | WebGL can fail on some phones | Fall back to the table view; test on iPhone Safari | P1 | To do (Kiro) |
| G9 | Judges must be able to install it | Fresh-machine test; pinned versions | P1 | Applied (pre-flight) |

## H. Kiro implementation

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| H1 | Judges look for *experimentation* | Run 4 small comparisons (spec vs. vibe, model vs. model, surface vs. surface, review loop vs. none); fill in `EXPERIMENTS.md` | P1 | To do (Kiro) |
| H2 | Hook impact is invisible | Hooks append to a log; report counts | P1 | To do (Kiro) |
| H3 | A property test catching a real bug is the best story | Screenshot the counterexample when it happens | P1 | To do (Kiro) |
| H4 | Steering’s value is invisible | Keep one before/after example (e.g., copy before and after `voice.md`) | P1 | To do (Kiro) |
| H5 | Agent safety should be visible | Show least-privilege permission configs in the write-up | P1 | To do (Kiro) |
| H6 | Our MCP server needs real use | The Crew App answers Discord questions through it | P1 | Applied |
| H7 | Variety of surfaces | IDE, CLI, Web, Crew, and Mobile (approving a paused workflow step) | P1 | Applied (plan) |
| H8 | Workflow evidence disappears | Commit curated workflow run reports | P1 | To do (Kiro) |
| H9 | Credits can run out silently | Simple credits ledger per person | P1 | To do (team) |

## I. Innovation

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| I1 | The idea is stronger as a reusable method | Publish a short “stayed-fixed rate” method spec any Open311 city can run | P2 | To do (Data) |
| I2 | Results should be checkable | Publish the zombie dataset with a data card | P1 | Applied (should-have) |
| I3 | Timely finding | Before and after the 2025 system change | P1 | Applied |
| I4 | Unusual lens | Reliability analysis (how long fixes survive), uncommon in civic tech | P0 | Applied |

## J. Presentation

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| J1 | Video structure | Cold open → speed vs. durability → map → proof → Kiro → who it’s for → close | P1 | Applied |
| J2 | Authenticity | Team on camera for about 5 seconds; real voices | P1 | Applied (voice rules) |
| J3 | Phone viewing | Captions; 1080p; legibility check on a phone | P1 | To do (Story) |
| J4 | Judges may not open the app | 6–8 gallery images plus a time-lapse GIF; the “Try judge mode” link first | P1 | To do (Story) |
| J5 | Demo polish | Rehearse with cached data; no loading spinners on screen | P1 | To do (Story) |
| J6 | Blog angle | Pick early, e.g., “We pre-registered our zombie definition” | P1 | To do (Story) |

## K. Impact

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| K1 | Impact needs real people | 3–5 interviews plus 1–2 hands-on trials, with consented quotes | P1 | To do (Story) |
| K2 | Who to ask | A neighborhood association, a councilor’s office, a local reporter who covers 311, a frequent 311 reporter | P1 | To do (Story) |
| K3 | Fairness to the city | Optional heads-up and right of reply | P1 | Applied (pre-flight) |
| K4 | Life after the hackathon | “What’s next”: other Open311 cities; the method spec | P2 | To do (Story) |

## L. Ethics, legal, privacy

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| L1 | People-related cases and private homes are sensitive | Out of scope | P0 | Applied |
| L2 | Blame | Departments and areas only, never individuals | P0 | Applied |
| L3 | Equity comparisons can mislead | Reporting-intensity context; “floor” language | P0 | Applied |
| L4 | City marks | CityScore® and BOS:311 used descriptively only; no seal | P0 | Applied |
| L5 | Mistakes will happen | Public corrections log | P1 | Applied |

## M. Team and process

| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| M1 | Decisions get lost | `DECISIONS.md` (also great write-up material) | P1 | Applied (template) |
| M2 | Cadence | Daily async standup; Sunday demo; freeze Dec 2 | P1 | To do (team) |
| M3 | Single points of failure | A backup owner for every critical item | P1 | To do (team) |

---

## N. Consistency fixes made across our own documents

| Where | Was | Now |
|---|---|---|
| Write-up, design | “Dark Boston basemap” | Concrete/asphalt with spray-paint pink |
| Write-up, architecture | “Static site plus a tiny API”; runtime AI for the Coroner | Fully static; no runtime AI calls; cached labels |
| Write-up, repo layout | `/mcp-analyze-boston/`, `/power/` in the main repo | `/mcp/`, `/schemas/`; Power and data repos are separate |
| Write-up, Crew App | Crew runs the nightly scan | GitHub Actions in the data repo refreshes nightly; Crew handles labeling, Discord Q&A, and the weekly report |
| Write-up, hosting | “AWS is a natural fit” | Netlify (via its Power) or GitHub Pages |
| Write-up, MCP and Power | “Analyze Boston MCP,” “Boston Open Data Power” | Third-party CKAN server for development; our Undead 311 MCP server; `boston-311-power` |
| Write-up, data | Street segments “verify”; system switch vague | Segments and addresses confirmed public domain; switch dated to August 2025, with most in-scope types moved by mid-2026 |
| Write-up, property tests | Monotonic zombie counts | Monotonic candidate pairs, plus 4 new properties |
| Steering, definition | Ambiguous attribution; no incidents or chains | Full algorithm (incidents, attribution, chains, follow-ups, cross-system) |
| Steering, tech | “Dark theme” | Removed; design-system governs |

## O. Still uncertain (verify in week 1)

- Whether CityScore’s published targets are current.
- NOAA access method.
- The exact new-system field names and type taxonomy (the kickoff session verifies these).
- Crew App manifest details (follow the Crew docs during build).
- Whether an Open311 key is worth requesting (optional).

## Second pass: what the first pass missed

### P. Red team: how skeptics would attack it
| Skeptic | Attack | Answer now built in | Status |
|---|---|---|---|
| Statistician | “Reports cluster in busy places, so your neighborhood baseline makes coincidence look rare.” | Primary baseline is now **the same spot as its own control**: the re-report rate right after a closure vs. the same segment’s typical rate in comparable windows (same season). The neighborhood model is secondary | Applied |
| Statistician | “50 field checks can’t support a precision number.” | 60–80 checks. At 50 the 95% interval is about ±12 points; at 80 about ±9 | Applied |
| City official | “You visited months later. It could have broken again since.” | Field checks only on **recent** zombies (re-reported within ~60 days of the snapshot); older ones are judged from records | Applied |
| Judge | “The zombie in your demo might be wrong.” | Judge mode uses only zombies confirmed in validation | Applied |
| Judge | “The video’s numbers don’t match the site.” | Video, README, and judge mode all use the frozen snapshot; live data is labeled as latest | Applied |
| Accessibility advocate | “A map-only, pink-on-grey, animated interface.” | Table view, measured contrast, shape plus color, reduced motion, single-copy cards on phones | Applied |
| Security reviewer | “Third-party fonts, tiles, and scripts.” | Self-hosted fonts and basemap extract; CSP; audits; pinned actions | Applied |
| Urban researcher | “311 reports reflect who bothers to report, not just conditions.” | Reporting-intensity context; optional consult with Northeastern’s BARI, which built neighborhood “custodianship” measures from Boston 311 data | Applied / To do |

### Q. Kiro build mechanics: cost, safety, correctness
| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| Q1 | The product steering file always included the full write-up (about 8,800 tokens) on **every** request; always-on context would have been about 12,600 tokens | The write-up now loads only via `#project`; always-on is about 3,800 tokens | P0 | Applied |
| Q2 | Hooks called Makefile targets that didn’t exist (`test-fast`, `validate`, `coroner-eval`) | Added to the structure steering, so the kickoff creates them | P0 | Applied |
| Q3 | The guard hook blocked *all* `.kiro` writes, but workflows store run files in `.kiro/workflow-runs/` and tick tasks in `tasks.md` | Allow those; still block steering, settings, hooks, and agents | P0 | Applied |
| Q4 | The Kiro-log hook was an agent prompt on Stop, and a workflow fires Stop once per step, so it would spend credits every step | Now a command hook; one narrative line per workflow run | P0 | Applied |
| Q5 | Per-save hooks would run tests on every file write during the build | Disabled during big runs; the workflow’s gates run the tests | P0 | Applied |
| Q6 | Parallel branches editing shared files would collide | Shared files scaffolded first; file-ownership list per branch | P0 | Applied |
| Q7 | The DuckDB MCP server could catch the database mid-rewrite | Pipeline builds to a temp file and renames it | P0 | Applied |
| Q8 | Reviewers and implementers could edit steering | Reviewers read-only; implementers barred from `.kiro` config | P0 | Applied |
| Q9 | Copy-lint on all of `web/src` would flag code | All interface text lives in `web/src/copy/en.json` and `es.json`; lint those plus docs | P1 | Applied |

### R. Data and methods, second look
| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| R1 | Research at Northeastern’s BARI shows 311 reporting reflects neighborhood “custodianship,” and they validated it against objective checks | Cite as precedent; consider their neighborhood measures for the reporting-intensity context (check the license) | P1 | To do (Data) |
| R2 | Reports cluster in hotspots | Same-spot baseline | P0 | Applied |
| R3 | Repaving can end a location’s “life,” which the survival curves can’t see | State it as a limitation; join street-construction data only if time allows | P2 | To do (Data) |
| R4 | Field visits long after a re-report mean little | Recent-only sample | P0 | Applied |
| R5 | Small validation sample | 60–80 | P0 | Applied |

### S. Product, design, presentation, second look
| # | Finding | Refinement | Pri. | Status |
|---|---|---|---|---|
| S1 | Thousands of SVG markers would be slow | Sprite atlas of 3–5 scanned circles (deck.gl icon layer) | P1 | Applied |
| S2 | A triplicate form is unreadable on a phone | Single copy in a bottom sheet on phones | P1 | Applied |
| S3 | Outside font and tile services must survive until Jan 29 | Self-host both | P1 | Applied |
| S4 | Copy scattered through components is hard to rewrite by hand | Central copy files | P1 | Applied |
| S5 | The rules ask for footage on the device it’s built for | Film both phone and desktop | P1 | To do (Story) |
| S6 | An honest failure is memorable | Show the Skeptic killing a false zombie in the video | P1 | To do (Story) |

### T. Rules fine print
| # | Finding | Refinement | Status |
|---|---|---|---|
| T1 | Social Blitz entries from mismatched profiles can be disqualified | Post from a profile matching your Devpost identity | Applied (pre-flight D7) |
| T2 | The Crew App bonus is judged only among the top 50 | Don’t over-invest in Crew before the core is strong | Noted |
| T3 | Blog credits go to the top 100 by score | Still worth it; low effort | Noted |

### U. Team and calendar
| # | Finding | Refinement | Status |
|---|---|---|---|
| U1 | Thanksgiving and finals squeeze the last two weeks | Front-load the build; freeze Dec 2 | To do (team) |
| U2 | Natural allies: BARI at Northeastern, and the Mayor’s Office of New Urban Mechanics (which built Street Bump and worked with BARI on 311 data) | Optional outreach for a methods check and an Impact quote | To do (Story) |

### V. Consistency check after the first pass
Also fixed:
- The write-up’s timeline still had Crew running a “nightly scan.”
- Its validation said 50; it now says 60–80 recent zombies.
- Its baseline section lacked the same-spot method.
- Its judge-mode wording, its agent list (now with reviewers), and its Kiro write-up outline (now with an Experiments item) were updated.

The playbook gained cost and safety troubleshooting rows. The pre-flight checklist gained A22–A26, B9–B10, C7b–c, and D7.

## Third pass: verification by execution, and scope by subtraction

The first two passes reviewed the plan by reading it. This one tested it: a throwaway dry run of the zombie rules on synthetic cases, a scripted check of every starter-kit file, and a deliberate effort to *remove* scope.

### W. Dry run of the zombie definition (executed)
| # | Finding | Fix | Status |
|---|---|---|---|
| W1 | **Bug:** grouping closed cases by close dates swallowed a fast resurrection. A pothole closed on day 1, re-reported on day 2, and closed again on day 4 merged into one incident, leaving **zero** zombies. The fastest, most damning failures would have vanished | A case joins an incident only if it was reported *before* the incident’s first closure (a true duplicate); maximum span 7 days. New property test 18 and a test-town case | Applied |
| W2 | Long street segments could match cases at opposite ends | Segment matches also require being within 75 m | Applied |
| W3 | A resident re-report after a “made safe” closure was ambiguous | Still a possible zombie, tagged “after temporary fix,” which enables a new finding: how often temporary fixes come back | Applied |
| W4 | Extra re-reports of the same problem were discarded | `reports_after` counts them as evidence strength | Applied |
| W5 | If an agent writes both the detector and the test-town answer key, the test proves nothing | A person writes the expected output by hand first; the guard hook blocks agents from editing it | Applied |

### X. Scripted check of the starter kit
- `mcp.json` parses.
- All 13 steering files have front matter on the first line with valid YAML and valid inclusion modes. The auto-inclusion file has its name and description.
- **Found and fixed:** leftover `data/processed/` paths in the tech steering, an agent prompt, and a spec prompt contradicted the decision to keep data outside the repo in `$DATA_DIR`.
- Files that are referenced but get created later (METHODS.md, VALIDATION.md, the Coroner labels, SNAPSHOT.md, agents, hooks) are expected to be missing at this stage.

### Y. The biggest remaining data risk
The new system, introduced type by type from August 2025, renamed fields (`open_date`, `close_date`, `service_name`, `assigned_department`). Nobody has yet confirmed that coordinates and closure text survived in the new data. That matters because validating *recent* zombies depends entirely on post-change records.
- **Added:** a day-1 go/no-go in the kickoff prompt.
- **Fallbacks:** match addresses to the city’s address registry if coordinates are missing; if closure text is missing, the planned-follow-up rule can use only source and timing.

### Z. Scope by subtraction
Each earlier pass added scope. Three students have five weeks in the middle of a semester, so this pass removes some.

| Layer | Contents | Target |
|---|---|---|
| 1. Demo-critical path | Ingest, detector, Coroner labels, map, autopsy cards, two-number scorecard, judge mode | Nov 15 |
| 2. Credibility | Same-spot baseline and excess, survival curves, funnel plots, methods page, validation | Nov 22 |
| 3. Delight | “Check my street,” repeat offenders, time-lapse, share images | If layers 1–2 are done |
| 4. Bonus | Crew App, Power | Last |

**Dropped:**
- **Weather adjustment:** redundant, since the same-season, same-spot baseline already absorbs freeze-thaw surges.
- **Street Bump revival:** reduced to one line in the video.
- **A second city.**
- **“Tomorrow’s zombies.”**

### AA. Judging simulation (where the score will be decided)
| Criterion | Likely range | What decides it |
|---|---|---|
| Impact | 7–8 | The validation number plus 2–3 real users who’ve tried it |
| Kiro use | 9–10 | Whether the experiments and evidence actually get documented |
| Design | 8–9 | Executing the spray-paint and city-form identity well |
| Innovation | 9 | The durability metric and same-spot baseline, if explained clearly |
| Presentation | 8–10 | The video |

**Weakest links:** Impact evidence and Presentation execution. Start user conversations in week 1, and storyboard the video by Nov 15.

### AB. Privacy in display
On residential streets, repeat offenders driven by resident reports are shown at block level, so the map never singles out a home. *Applied.*

### AC. Where plan audits stop paying off
Three passes over a plan have reached diminishing returns. The next reviews that can find real problems need real artifacts:
1. **After the kickoff:** the verified data dictionary and the go/no-go result.
2. **After the one-shot build:** the code, the test-town results, the first map.
3. **Before the freeze:** the video and the write-up.

Schedule those three reviews instead of a fourth plan audit.

## Sources for new findings

- The 2025 system change (from August 2025) and field renames: https://cdn.jsdelivr.net/gh/sgarcese/Civic-Analytics-Agent-Workflow-Claude-Skill@main/SKILL.md
- Source channel values: https://sunli-lisun.github.io/ac221/data-sources.html
- Dataset page and CRM Value Codex: https://data.boston.gov/dataset/311-service-requests
- Placeholder coordinates example: https://course.ccs.neu.edu/ds2500sp23/proposals/27.html
- Data volume (2021): https://baselight.app/u/kaggle/dataset/doshiharmish_311servicerequestboston2021
- SAM street segments: https://data.boston.gov/dataset/boston-street-segments-sam-system · SAM addresses: https://data.boston.gov/dataset/fc9562ca-02df-40bf-b4db-a36effb52ccc
- Boston Globe pothole tracker: https://apps.bostonglobe.com/metro/2024/02/boston-potholes-tracker
- CityScore (trademark, dataset): https://www.bostonglobe.com/metro/2016/08/17/city-hall-always-above-average-you-ask-city-hall/GUvNcsQlIhJYt8SPgjLzCN/story.html · https://data.boston.gov/dataset/cityscore
- Creatio rollout: https://www.pulse.bot/cio-pulse/news/how-boston-is-transforming-its-outdated-311-system-8037fa30-74a8-444b-8710-26a7f72585d8
- New-system field names: https://cdn.jsdelivr.net/gh/sgarcese/Civic-Analytics-Agent-Workflow-Claude-Skill@main/SKILL.md
- BARI and 311 custodianship: https://cssh.northeastern.edu/bari/projects/past-projects/custodianship-in-the-urban-commons/ · objective validation (244 streetlight outages): https://wiki.santafe.edu/images/1/12/GSSS.Lecture.1.OBrien.07.16.2019.pdf · BARI and New Urban Mechanics on 311: https://businessinsider.nl/how-a-partnership-between-the-city-of-boston-and-local-universities-is-working-to-help-policymakers-better-serve-residents/
