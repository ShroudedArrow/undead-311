# The Undead 311 — Project Write-up

**Kiroween 2026 · Frankenstein category · Team of 3 students**
*Living document. Last updated Thu Nov 12, 2026 (solo project, timeline re-baselined). Deadline: Fri Dec 4, 2:00 PM PT. Start with `START_HERE.md` in the repo.*

---

## 1. One-paragraph pitch

Boston marks 311 problems “closed.” Some of them don’t stay dead.

**The Undead 311** finds service requests the city closed that were re-reported at the same spot soon after. It separates real resurrections from coincidence with statistics, and raises each one as a zombie on a haunted map of Boston. Every case gets an “autopsy report” with the evidence.

It also adds the metric the city’s own scorecard is missing. Boston’s CityScore grades departments on *how fast* cases close. We add **whether the fix stayed fixed.**

A crew of Kiro agents re-checks the city’s data every night and posts a weekly “Resurrection Report” to Discord.

---

## 2. The problem and the evidence

| Evidence | Source |
|---|---|
| A 7News spot check of 22 broken-sidewalk reports found **nine marked “fixed” or “made safe” that looked unchanged** from the original photos | WHDH 7 Investigates |
| Boston has mass-closed old cases with a form notice saying 311 is **“closing out backlogged service requests”** | Public case pages, 311.boston.gov |
| Kansas City’s 311 audit found the meaning of “closed” was **left to each department**, from “work order created” to “inspection verified the fix” | KCMO Performance Audit, 2015 |
| In 2026, an independent SF 311 app found **425 drug complaints cancelled** without being addressed | San Francisco Standard |
| Citywide, **78% of Boston tickets closed on time** (Jan 1 – Oct 4, 2024). Residents interviewed said requests were closed while the issue wasn’t fully fixed | Dorchester Reporter |
| CityScore’s published targets are about speed, e.g. **potholes: 80% completed within 1 business day** (older published targets; confirm current ones) | City of Boston CityScore documents and dataset |

**The gap:** the city measures speed of closure. Nobody publicly measures **durability**: whether a closed problem stays closed. A metric that only rewards fast closure can quietly reward closing cases that aren’t really fixed.

---

## 3. Who it’s for

| User | What they get |
|---|---|
| **Residents who report problems** | Proof their neighborhood’s issues keep coming back, plus a link to re-report through official channels |
| **City councilors and staff** | A one-page report card per council district |
| **Neighborhood associations** | Zombie maps and trends for their area |
| **Local journalists** | Shareable permalinks, the evidence behind each zombie, and an open dataset |
| **311 and department managers** | Durability metrics for internal quality checks; framed as a feedback tool, not a gotcha |

---

## 4. Prior art: why this is new

| Existing work | What it does | What it doesn’t do |
|---|---|---|
| **RentSmart Boston** (city) | Shows 311 complaints and violations by address | Doesn’t check whether closures held |
| **StreetSmart / Augrented** | Building reports for renters | Same; renter-focused |
| **SolveSF** (San Francisco) | One-off analysis of cancelled complaints | Not systematic or ongoing; one city, one issue type |
| **TV and newspaper spot checks** | Manual investigation of a handful of cases | Not scalable |
| **Boston Globe pothole tracker** | Maps open and closed pothole requests by neighborhood | Shows volume, not whether fixes held |
| **CityScore** (city) | On-time closure rates | No durability measure |

We found **no tool that systematically detects “closed, then re-reported” cases**, separates them from coincidence, and scores departments on durability. Devpost galleries aren’t fully searchable, so this is “not found,” not “proven new.”

---

## 5. The data

| Dataset | Use | License / access |
|---|---|---|
| **Boston 311 Service Requests** (Analyze Boston; yearly files since 2011, updated daily) | Core data: type, department, queue, open and close times, coordinates, closure reason, closed photo (sparse) | **Open Data Commons PDDL** (public domain) |
| **NOAA daily weather, Boston Logan** | Freeze-thaw cycles, so new winter pothole damage isn’t counted as failed fixes | US government, public domain *(confirm API token needs)* |
| **Boston street segments (SAM)** | Match cases along the same block instead of by raw radius | **PDDL**, updated nightly |
| **Boston SAM addresses** | “Check my street” address search, done in the browser | **PDDL**, updated nightly |
| **Council districts and neighborhoods** | District report cards | Analyze Boston *(verify license)* |
| **Boston Open311 API** (optional) | Live feed of new requests | Requires an API key on request |

**Known data issues**
- **System switch:** Boston’s 311 system changed with **the 2025 system change (new system from August 2025; most in-scope types moved by mid-2026)** (moving onto Creatio, a cloud-based CRM), and the open data uses different field names before and after. Map both formats into one schema in week 1, with a case-type crosswalk so a closure in the old system can match a re-report in the new one. This also becomes a natural experiment (section 7.8).
- **City-originated cases:** the source field includes values such as Employee Generated, City Worker App, and Maximo Integration. Planned follow-up work (a temporary “made safe” repair, then a permanent one) can look like a zombie, so it gets its own category, and results are shown with and without city-originated re-reports.
- **Placeholder coordinates:** some cases carry a default location (such as City Hall). Detect and exclude high-frequency default points.
- **Value meanings:** use the dataset’s CRM Value Codex to interpret codes.
- **New-system field names** include `open_date`, `close_date`, `service_name`, and `assigned_department`. **Day-1 go/no-go:** confirm the data from the 2025 system change (new system from August 2025; most in-scope types moved by mid-2026) still has coordinates (or addresses that match the city’s address registry) and closure text. Field validation of recent zombies depends on it.
- **Photos:** the photo fields are mostly empty, so don’t plan around them.
- **Closure-reason text** is messy and partly templated. That’s what the Coroner agent handles.
- **Free text may contain personal information** (names, phone numbers, emails). Scrub it before anything is displayed.

---

## 6. Features by priority

**Cut lines (scope by subtraction).** Build in layers, and don’t start a layer until the one before it works:
1. **Demo-critical path, by Tue Nov 17:** ingest, zombie detector, Coroner labels, haunted map, autopsy cards, the two-number scorecard, judge mode. Enough to storyboard the video.
2. **Credibility layer, by Sun Nov 22:** same-spot baseline and excess, survival curves, funnel plots, methods page, validation numbers.
3. **Delight layer:** “Check my street,” repeat offenders, time-lapse, share images.
4. **Bonus layer:** Crew App, Power.

**Dropped to protect focus:** weather adjustment (the same-season, same-spot baseline already absorbs freeze-thaw surges), a second city, “tomorrow’s zombies,” and Street Bump (section 13).

### Must-have (done by Sun Nov 22)
1. **Ingest pipeline:** 311 data from 2015 onward into DuckDB/Parquet, plus nightly updates.
2. **Zombie detector** (section 7.1): street-segment matching, incident clustering, zombie chains (“risen N times”), and planned follow-ups.
3. **Comparison baseline and excess resurrections** (section 7.2), so we can say how many zombies are more than coincidence.
4. **Coroner agent:** classifies each closure’s text. Labels: resolved / noted / invalid / duplicate / referred / made safe (temporary) / planned follow-up / bulk backlog closure / other.
5. **Bulk-closure detector:** days when large numbers of cases closed with identical text.
6. **Haunted map:** zombies rise where problems returned. Filter by neighborhood, department, case type, and year.
7. **Autopsy-report evidence cards:**
   - **Cause of death:** the closure classification.
   - **Time in the grave:** days between closure and re-report.
   - **Resurrection date.**
   - Both case records, the confidence score, and the Skeptic’s objections.
8. **“Stayed-fixed on-time rate”** per CityScore-style category (section 7.5).
9. **Survival curves:** how long fixes last (section 7.3).
10. **Department and neighborhood comparisons**, with small-sample correction and funnel plots (section 7.4).
11. **Methods page:** definitions, baseline, validation, limitations.
12. **Validation sample**, hand-checked in the field (section 8).
13. **Judge mode:** a 60-second guided tour of three zombies chosen only from the confirmed validation set, running on the frozen judging snapshot. No login, fast on phones.
14. **Kiro Crew App** (separate repo): daily labeling of new closure texts, the weekly Discord “Resurrection Report,” and Discord questions like “any zombies near Dudley St?” answered through our MCP server. The nightly data refresh itself runs from GitHub Actions in a separate data repo.
15. **“Check my street” address search**, built from the city’s address registry.
16. **Repeat offenders:** locations that died and rose three or more times.
17. **Data freshness and corrections:** a “Data as of” date, nightly status, and a “Report an error” link with a public corrections log.

### Should-have (done by Nov 26)
- **Creatio before/after comparison** (section 7.8).
- **Weather adjustment:** dropped (see the cut lines above).
- **Interactive methods sliders:** switch radius, window, and matching mode instantly from precomputed results.
- **Share images** for each zombie and neighborhood, for social posts.
- **The data connector packaged as a Kiro Power.**
- **District report cards** (one page each).
- **Permalinks** for every zombie.
- **Spanish** for the evidence cards and reports.
- **“Night of the Living 311” time-lapse:** zombies rising across Boston, 2015–2026.
- **Accessibility:** a sortable table view mirroring the map, keyboard navigation, reduced-motion support.
- **Open zombie dataset** published under an open license.
- **3–5 user interviews**, with one quote used in the video.

### Stretch (only if all must-haves are done by Nov 19)
- **Street Bump revived** (section 13).
- **“Tomorrow’s zombies”:** score each closure when it happens by how likely it is to come back. Test it on past years first.
- **A second Open311 city**, to show the method generalizes.
- **A “still broken?” one-tap confirmation** for residents, which doubles as labeled data.

---

## 7. Methods

### 7.1 Zombie definition (v1; lives in `zombie-definition.md` steering)
A closed case **C** (closed at time *t_c*, location *x*, type *k*) is a **possible zombie** if there is a later case **R** where all of these hold:
- R opens **after** C closes, within **D days** (default 60).
- R is the **same type, or the same type family**, as C.
- R is within **R meters** of C (default 30 m), or on the **same street segment** once segment matching exists.
- R is not a duplicate opened *before* C closed.

Cases closed as “invalid” or “duplicate” are tracked separately. They’re a different kind of death.

**Refinements**
- **Incidents first (true duplicates only):** a closed case joins an incident only if it was reported *before* the incident’s first closure, while the problem was still “alive.” A case opened after a closure is never merged in; it can only be a resurrection. Grouping by close dates alone would swallow a fast resurrection into its own original. A dry run on synthetic cases confirmed that bug before it reached the build.
- **Attribution:** re-reports are processed in time order. Each attaches to the most recent eligible incident (ties broken by case ID), so every re-report counts once.
- **Chains:** when a resurrection is closed and the problem returns again, the chain grows. Locations that rose three or more times are “repeat offenders.”
- **Planned follow-ups:** a re-report that is city-originated and follows a “made safe” or “referred” closure is classed as a planned follow-up, not a zombie.
- **Across systems:** matching uses location, time, and the case-type crosswalk, so old-system closures can match new-system re-reports.

Every possible zombie gets a **confidence score**, built from:
- distance,
- time gap,
- how specific the case type is,
- the closure classification,
- the local baseline rate,
- the Skeptic’s surviving objections.

### 7.2 Comparison baseline (is it more than coincidence?)
**Primary: the same spot as its own control.** Reports cluster in busy places, so a citywide rate understates coincidence. For each street segment, compare the re-report rate in the window right after a closure with the same segment’s rate in comparable windows (same season) that did not follow a closure. The difference is the excess.

**Secondary: neighborhood rate.** For each closed case, estimate how often a same-type report would appear nearby anyway:
- Use that area’s normal report rate for the season, excluding the window around the case.
- With rate λ (reports per square meter per day), match area A, and window D:
  - P(at least one by chance) = 1 − e^(−λ·A·D)
  - Expected count = λ·A·D

**Excess resurrections** = observed zombies − expected zombies. Report this by department, case type, and neighborhood.

**Robustness check.** Shift closure dates by random offsets, keeping locations fixed, about 1,000 times. See how many “zombies” appear by chance alone.

### 7.3 How long fixes last (survival analysis)
- For each closed case, measure the time until its first re-report. Cases with no re-report by the end of the data count as “still holding” (censored).
- **Survival curves:** the share of fixes still holding after 7 / 30 / 90 days, by department and case type.
- **Fix half-life:** the median time a fix holds, where defined.

This is reliability analysis from industrial engineering, applied to city repairs.

### 7.4 Fair comparisons
- **Small-sample correction:** groups with few cases are pulled toward the citywide rate, so tiny departments don’t look extreme by chance.
- **Funnel plots:** each group’s rate against its case count, with control limits. Only real outliers fall outside.
- **Uncertainty:** show a confidence interval on every rate.

### 7.5 The “stayed-fixed on-time rate”
- **Raw:** the share of cases closed on time *and* not resurrected within D days.
- **Adjusted:** the same rate, with expected coincidences removed (section 7.2).

Shown beside the plain on-time rate for each category (potholes, streetlights, graffiti, signals, and so on). The gap between the two numbers *is* the story.

### 7.6 Weather adjustment (dropped)
The primary baseline compares each spot with itself in the same season, which already absorbs winter freeze-thaw surges. A separate weather join isn’t worth the added complexity.

### 7.7 Street-segment matching
Match cases along the same street segment instead of a raw radius. That avoids false matches across intersections or on parallel streets.

### 7.8 Natural experiment: the Creatio switch
Compare resurrection rates **before and after** each service type moved to the new system. Use types that haven’t moved yet as a comparison group. Report it carefully: the format change itself can create artifacts.

### 7.9 Reporting bias (zombie counts are a floor)
A zombie only appears if someone reports the problem again. Neighborhoods that report less will show fewer zombies even if fixes fail just as often. We show rates alongside local reporting intensity, call measured rates a floor, and keep neighborhood comparisons cautious.

### 7.10 Coroner accuracy
Hand-label about 200 closure texts. Report the Coroner’s accuracy and its most common confusions. A hook reruns this check whenever the Coroner changes.

---

## 8. Validation plan (credibility is everything)

1. **Draw a random sample of 40–50 recent possible zombies** (re-reported within about 60 days of the snapshot, so a visit still means something). Solo shortcut: sample within 3–4 neighborhoods you can reach easily, and say so in the write-up. At 50 the 95% interval is roughly ±12–13 points; at 40 about ±14. Older zombies are judged from case records only.
2. **Check each one, twice:** you check each site in person (we’re in Boston) and photograph it; a volunteer friend then rates the same cases independently from your photos and the case records. Neither rater sees the confidence score. Report how often you agree (Cohen’s kappa).
3. **Label each:** real zombie / new, unrelated problem / can’t tell.
4. **Report precision** (the share that were real zombies) with a 95% confidence interval, on the methods page, in the README, and in the video.
5. **Sensitivity panel:** how results change as R and D vary, so judges can see the definition isn’t cherry-picked.
6. **Optional:** a sample of non-zombie closures, to estimate what we miss.

**Language rules** (in `language.md` steering):
- Always “possible zombie.”
- Never “the city lied.”
- Aggregate to departments and neighborhoods; never name individual workers.
- Every claim links to its evidence.

---

## 9. Architecture

```
Analyze Boston (CKAN API, daily) ─┐
NOAA weather ─────────────────────┼─► Ingest (Python) ─► DuckDB/Parquet
Street segments / districts ──────┘          │
                                             ▼
          Zombie detector ─► Baseline & excess ─► Survival / funnel / stayed-fixed
                 │                                          │
                 ▼                                          ▼
       Coroner + Skeptic agents                   Static JSON + map tiles
                 │                                          │
                 └──────────────► Web app (React + MapLibre) ◄┘
                                             ▲
  GitHub Actions in undead-311-data: nightly refresh ─► static data files
  Kiro Crew App (separate repo): labels, Discord Q&A, weekly report (reads the data files)
```

**Stack**
- **Pipeline:** Python, DuckDB, Hypothesis (property tests), a survival-analysis library, statsmodels.
- **Frontend:** React and MapLibre GL, with precomputed tiles for speed.
- **Hosting:** a fully static site (Netlify via its Kiro Power, or GitHub Pages). No server and no paid runtime APIs. JSON Schemas define every exported file, so the pipeline and the web app can’t drift apart.
- **Spend caps:** hard caps on every paid service through **Jan 29**.

**No runtime AI calls.** Most closure texts are templates. The Coroner agent labels the deduplicated templates during the build, the labels are cached in the repo, and the Crew App labels new templates weekly.

**Repo layout**
```
/.kiro/
  steering/      data-dictionary.md, zombie-definition.md, language.md, methods.md, product.md, tech.md
  specs/         ingest/, detector/, baseline/, coroner/, survival/, map-ui/, autopsy-cards/
  hooks/         kiro-log, data-validate, detector-revalidate, coroner-eval
  agents/        coroner, skeptic, cartographer, herald, data-steward
  workflows/     zombie-hunt.workflow.yaml
  settings/      mcp.json
/pipeline/   /web/   /mcp/   /schemas/
/docs/       METHODS.md, VALIDATION.md, KIRO_LOG.md, CRITERIA_MAP.md
LICENSE (MIT or Apache-2.0, visible in the GitHub About section)
README.md
```
**Separate repos** (same GitHub account): `undead-311-crew` (the Kiro Crew App), `boston-311-power` (the Power; Kiro installs Powers from a repo with POWER.md at its root), and `undead-311-data` (the nightly refresh, so the judged repo doesn’t change after the deadline).

---

## 10. Kiro plan (the Technological Implementation criterion)

| Kiro feature | How we use it | Evidence for the write-up |
|---|---|---|
| **Specs** | One spec per component. Requirements-first for the detector; the **bugfix spec workflow** when the Skeptic finds a real flaw | Spec count; one “Skeptic found a bug → spec fixed it” story |
| **Steering** | Data dictionary, zombie definition, language rules, methods, product, tech. File-match steering for pipeline code vs. UI code | Before/after examples where steering changed agent output |
| **Hooks** | **Kiro-log hook** (end of each agent session → append to `KIRO_LOG.md`) · **data-validate** (new data → format check + property tests) · **detector-revalidate** (detector change → rerun the validation sample and update precision) · **coroner-eval** (Coroner change → rerun the 200-text check) · **copy-lint** (flags banned phrases and leftover placeholders) · **guard** (blocks destructive commands) | Hook count; what each saved us |
| **Property-based testing** | Listed below | Number of properties; any bug a property caught |
| **Custom agents** | **Coroner** (classifies closure text; read-only tools), **Skeptic** (argues each zombie is a coincidence), **Cartographer** (builds map tiles), **Herald** (writes the weekly report), **Data Steward** (format and dictionary upkeep), and two read-only **reviewers** (statistics; UX and design) that run on different models in workflows. Project agents committed under `.kiro/` also apply in Kiro cloud sessions | Agent configs in `.kiro/agents/` |
| **Kiro workflows** (new Sept 30, 2026) | **Zombie-hunt recipe:** ingest → detect → Coroner → Skeptic loop (repeat until no objection survives) → report. Parallel branches per case type. Background runs | The recipe file in `.kiro/workflows/`; run logs |
| **MCP** | Development: Context7 (library docs), DuckDB (agents query the real data), CKAN (dataset discovery), Playwright (UI checks and screenshots). Product: our **Undead 311 MCP server** (zombies near a point, department durability, case autopsy, weekly summary), used by the Crew App | Configs in `.kiro/settings/mcp.json`; server code in `/mcp/` |
| **Kiro Powers** | Our **boston-311-power** (POWER.md + MCP config + steering), plus a hosting Power (e.g., Netlify) | The Power repo; install instructions |
| **Kiro Crew** | The separate Crew App: daily closure-text labeling, Discord Q&A through our MCP server, the weekly report, and a “Zombie of the Week” | The separate repo (for the Crew App bonus) |
| **Surfaces** | IDE for specs and property tests; CLI for the pipeline and agents; Web cloud sessions for reviews and workflows; Crew for scheduled jobs; Mobile to approve a paused workflow step | `docs/EXPERIMENTS.md`: controlled comparisons (spec vs. vibe, model vs. model, surface vs. surface) |

**Property-based tests (minimum set)**
1. A case is never its own zombie.
2. A zombie’s re-report always opens strictly after the original closure.
3. All rates stay between 0 and 1.
4. A larger radius or longer window never removes a *candidate pair* (final zombie counts can shift when incidents merge).
5. Results don’t depend on input row order.
6. Survival curves start at 1 and never rise.
7. Excess counts are reproducible for a fixed random seed.
8. Corrected group rates always lie between the group’s raw rate and the citywide rate.
9. The Coroner only outputs labels from the allowed set.
10. The stayed-fixed rate never exceeds the on-time rate.
11. Distance is symmetric and never negative.
12. Incident clustering assigns every closed case to exactly one incident.
13. Each re-report is attributed to at most one incident.
14. Moving every case by the same small offset changes nothing (translation invariance).
15. Every exported file validates against its JSON Schema.

---

## 11. Design (the Design criterion)

- **Haunted map:** concrete and asphalt tones (no default dark theme), with spray-paint circles in survey pink where problems came back. Full rules in `design-system.md`.
- **Autopsy-report cards:** a coroner’s-form layout, with the evidence front and center.
- **Leaderboards:** funnel plots and corrected rates, never raw rankings alone.
- **The two-number scorecard:** “Closed on time” next to “Stayed fixed.”
- **Judge mode and guided tour:** three confirmed zombies, 60 seconds, on the frozen snapshot.
- **Accessibility:**
  - a table view mirroring the map,
  - keyboard navigation and good contrast,
  - reduced-motion support (every spooky animation is skippable),
  - Spanish for evidence cards and reports.
- **Sharing:** permalinks, district report cards, and open data downloads.

---

## 12. Demo video (Presentation criterion and Best Demo bonus)

**Rules:** under 3 minutes, public on YouTube, shows the app working. **No copyrighted music. No third-party logos or trademarks.**
- Use original or royalty-free audio.
- Blur or crop logos, including chat-app branding and official city marks, when showing screens.

| Time | Beat |
|---|---|
| 0:00–0:15 | **Cold open on location:** a real case page reading “resolved,” next to the unchanged problem on camera |
| 0:15–0:35 | “Boston grades 311 on speed. Nobody checks whether fixes stay fixed.” The two-number scorecard |
| 0:35–1:05 | The “Night of the Living 311” time-lapse. Click a zombie: the autopsy card and the Skeptic’s verdict |
| 1:05–1:30 | Credibility: excess over chance, survival curves, a funnel plot, and “**X of 50** confirmed in person” |
| 1:30–1:45 | The Creatio before/after, or the stayed-fixed scorecard by category |
| 1:45–2:30 | **The Kiro story:** a property test catching a bug, the monster-hunter crew in a workflow, the Crew App posting the weekly report, the Power |
| 2:30–2:50 | Who uses it, a real user quote, and “any city with open 311 data” |
| 2:50–2:55 | Title card and URL |

**Production:** script by Nov 20 · field footage Nov 20–26 · first cut Nov 29 · final Dec 2.

---

## 13. Street Bump revived (recommended: drop)

*Third-pass recommendation: drop this. The core plan already fills five weeks for three students; keep the story as a single line in the video (“Boston tried to crowdsource potholes in 2012”) instead of building it.*

**The story.** In 2012 Boston launched **Street Bump**, an app that used a phone’s accelerometer and GPS to detect potholes automatically. Adoption stalled: of 19,000 potholes reported in 2014, 16,000 came from city employees. Its rule was that a bump became a pothole once **at least three people** hit it in the same spot.

**The revival.** A browser-based Street Bump (using the phone’s motion sensors) that **confirms whether a suspected zombie pothole is still there.** It gives us a Resurrection element inside the Frankenstein entry.

**Rules if we build it**
- **Passengers and cyclists only, never drivers holding phones.**
- Explicit permission prompt for motion sensors.
- Collect no trip history.

**Go only if** every must-have is done by Nov 19. It adds meaningful build risk.

---

## 14. Ethics and privacy

- Aggregate results to departments, neighborhoods, and districts. **Never** single out individual workers.
- Scrub personal information from free text before display.
- On residential streets, repeat offenders driven by resident reports appear at block level, not an exact point, so the map never singles out a home.
- Use “possible zombie” language, and show evidence and uncertainty everywhere.
- Include an “improving departments” view, so the tool rewards progress, not just failure.
- Share early findings with Boston’s analytics team as feedback. If they respond, ask permission before quoting them.

---

## 15. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| False positives (a new problem, not an unfixed one) | High | Baseline and excess counts, the Skeptic agent, the validation sample, adjustable R/D, confidence scores |
| Dataset format changes during the Creatio switch | Medium | Unified schema in week 1; turn it into the before/after study |
| Millions of rows slow everything down | Medium | DuckDB/Parquet, precomputed aggregates and tiles |
| Seen as attacking the city | Medium | Feedback framing, “improving” view, careful language |
| Scope creep | High | Strict must / should / stretch tiers; Street Bump only after Nov 19 |
| Credits run out (Crew agents use credits) | Medium | Every teammate requests 4,000 credits now; keep nightly jobs small |
| The app or data feed breaks during judging (Dec 16 – Jan 29) | Medium | Frozen data snapshot fallback, a pre-recorded walkthrough, spend caps, monitoring |
| Video includes trademarks or music | Low | Original audio; blur logos; final review against the rules |

**Pre-mortem: “it’s February and we lost because…”**
- **“The zombies weren’t real.”** Prevented by the baseline, the Skeptic, and the in-person validation.
- **“It looked like just a map.”** Prevented by autopsy cards, the two-number scorecard, and the Crew App.
- **“The Kiro use was shallow.”** Prevented by workflows, custom agents, property tests, hooks, a Power, and the Crew App, all documented with counts.
- **“Great project, weak video.”** Prevented by an early script, field footage, and a final cut by Dec 2.

---

## 16. Timeline and owners

*Update: this is now a solo project. Every role below is yours, and Kiro carries more of the build. Run the main repo through one build workflow (it parallelizes internally) and use separate sessions only for the separate Crew and Power repos and for read-only audits.*

**Roles**
- **D: Data & engine lead.** Pipeline, detector, statistics, validation.
- **K: Kiro & agents lead.** Steering, specs, hooks, agents, workflows, MCP, Power, Crew App, the Kiro log.
- **S: Design & story lead.** UI, accessibility, field footage, the video, blog and social posts, user interviews.

| Dates | Kiro does (overnight and in sessions) | You do (about 25 hours total) |
|---|---|---|
| **Thu Nov 12** | Setup guide (Gate 1); kickoff | Accounts, tokens, sandbox settings, upload the kit (about 1.5 h) |
| **Fri Nov 13** | Agents, hooks, spec drafts | Write the test-town answer key by hand (about 1.5 h) |
| **Sat Nov 14** | Smoke test; **first overnight build** | Review specs line by line (about 2 h) |
| **Sun Nov 15 – Tue Nov 17** | Fixes; second overnight build. **Demo-critical layer done** | Morning reviews (about 20 min/day) |
| **Wed Nov 18 – Fri Nov 20** | Credibility layer. **Fri: freeze the snapshot, draw the validation sample** | Morning reviews |
| **Sat Nov 21 – Sun Nov 22** | Power repo | Field validation (about 4 h) and photos to your second rater; 2 short user chats; spray-paint circles |
| **Mon Nov 23 – Wed Nov 25** | Delight layer only if on track; `make capture` media | Copy pass and design pass (about 3 h) |
| **Thu Nov 26** | — | *Thanksgiving* |
| **Fri Nov 27 – Sun Nov 29** | Channel export; traceability and stats | Video: script, record, edit (about 4.5 h) |
| **Mon Nov 30 – Tue Dec 1** | Final readiness check | Write-up and Devpost text (about 2 h) |
| **Wed Dec 2 – Thu Dec 3** | — | **Freeze Wed; submit Thu** (Fri Dec 4 is buffer) |
| **Dec 16 – Jan 29** | Nightly data refresh (GitHub Actions) | Watch for issues |

---

## 17. Submission checklist (from the official rules)

- [ ] Category: **Frankenstein**
- [ ] Bonuses entered:
  - [ ] Best Student Project (Frankenstein)
  - [ ] Best Kiro Crew App
  - [ ] Blog
  - [ ] Social Blitz
  - [ ] Ghost of Kiroween Past (if anyone registered in 2025)
- [ ] Public **GitHub** repo with all source code, assets, and instructions
- [ ] OSI license detectable in the About section
- [ ] `/.kiro` at the root and **not** in `.gitignore`
- [ ] Working app URL, judge mode, no login required; stays up until Jan 29
- [ ] Text description of features and functionality
- [ ] Demo video under 3 minutes, **public on YouTube**, no copyrighted music or third-party trademarks
- [ ] Kiro write-up covering: IDE / CLI / Web / Crew, custom agents, hooks, specs, steering, MCP, property-based testing, powers
- [ ] **Student details for all 3 members:** LinkedIn, student email, year and degree, school name
- [ ] Crew App: separate public repo URL plus a description (same GitHub account)
- [ ] Blog: public, on a third-party platform, published during the submission period, mentions Kiroween 2026
- [ ] Social: starts with `#KiroweenHackathon26`, says what we like about Kiro and how it changed our approach, original writing
- [ ] Disclose any pre-existing code (frameworks and libraries only)
- [ ] Data licenses listed in the README

---

## 18. Kiro write-up outline (mirrors the questions in the rules)

1. **Surfaces:** IDE vs. CLI vs. Web vs. Crew. What each was best at, from our experiments.
2. **Custom agents:** the monster-hunter crew. Why each exists and how it changed the build.
3. **Agent hooks:** each hook, the chore it automated, and its impact (the Kiro-log hook proves itself).
4. **Spec-driven development:** how specs were structured, requirements-first vs. bugfix, and a comparison with vibe coding.
5. **Steering:** which docs mattered most (likely the zombie definition and language rules), with examples.
6. **MCP:** the Analyze Boston server and what it made possible.
7. **Property-based testing:** which requirements became properties, and the bugs they caught.
8. **Powers:** the boston-311-power we built, and any Powers we used.
9. **Workflows:** the zombie-hunt recipe, its Skeptic loop, and what ran in the background.
10. **Experiments:** the controlled comparisons in `docs/EXPERIMENTS.md` (spec vs. vibe, model vs. model, surface vs. surface, review loop vs. none).
11. **What Kiro got wrong** and how we fixed it.

---

## 19. Prize strategy

An entry can win **one Overall or Category prize, plus any number of bonuses.**

| Prize | Amount | Our path |
|---|---|---|
| Overall 1st / 2nd / 3rd | $30K / $20K / $10K | Overall execution |
| Best Frankenstein | $5K | Category fit |
| Best Student Project (Frankenstein) | $1,500 + 1-year Kiro Pro Max | All-student team |
| Best Kiro Crew App | $1K | Separate repo; requires a top-50 finish |
| Best Demo | $1K | Top-10% overall plus the best Presentation score |
| Ghost of Kiroween Past | $2K | Only if someone registered in 2025 |
| Blog / Social | Credits / subscription | Low effort; do both |

---

## 20. Projected score (2026 rubric)

| Version | Impact | Kiro | Design | Innovation | Presentation | Penalties | /50 |
|---|---|---|---|---|---|---|---|
| Original concept | 7 | 8 | 8 | 8 | 8 | data −1 | 38 |
| + statistics and durability upgrades | 8 | 9 | 8 | 9 | 9 | data −1, build −1 | 41 |
| **This plan (must + should tiers)** | 8 | 10 | 9 | 9 | 10 | data −1, build −1 | **43** (range 39–45) |
| + Street Bump revival | 8 | 10 | 9 | 10 | 10 | data −1, build −2 | 44 (range 38–46) |

These are ceilings if executed well. The biggest remaining swing factors are **validation quality** and **the video.**

---

## 21. Open decisions

1. **Team roster:** three students, D / K / S roles assigned.
2. **Kiroween 2025 registrations?** Check for the $2K bonus.
3. **License:** MIT or Apache-2.0.
4. **Coroner:** settled. No runtime AI calls; labels are cached and the Crew App labels new templates.
5. **Hosting:** Netlify (via its Kiro Power) or GitHub Pages.
6. **Street Bump:** recommended dropped (section 13).
7. **City outreach:** whether and when to share early findings with Boston’s analytics team.

---

## 22. Start here

See `START_HERE.md` in the repo: the solo, minimum-hours checklist, exactly what to give Kiro in order, and the pre-start audit.

---

## Sources

- **Official rules and overview:** https://kiroween.devpost.com/rules · https://kiroween.devpost.com/
- **Boston 311 data and license:** https://data.boston.gov/dataset/311-service-requests · fields: https://sunli-lisun.github.io/ac221/data-sources.html · photo fields mostly empty: https://shaifalic15.github.io/Boston-311-Service-Requests/data.html
- **On-time rates and resident experience:** https://dotnews.com/node/196986
- **7News sidewalk check:** https://whdh.com/7-investigates/hank-investigates/hank-investigates-boston-repair-runaround/
- **Backlog closure notices:** https://311.boston.gov/reports/101002596254
- **Kansas City 311 audit:** https://kcmo.gov/home/showpublisheddocument/649/636953491950100000
- **SolveSF cancellations:** https://sfstandard.com/2026/08/21/sf-311-drug-reports-canceled/
- **CityScore targets:** https://Www.Boston.gov/sites/default/files/embed/file/2016-10/06_data_analytics.pdf · https://www.boston.gov/departments/analytics-team/cityscore
- **Creatio migration:** https://www.boston.gov/node/16481251 · https://hoodline.com/2026/02/boston-s-311-hotline-gets-quiet-heart-transplant-in-tech-shakeup/
- **Open311:** https://311.boston.gov/open311 · https://wiki.open311.org/GeoReport_v2/Servers
- **Data details:** source field values: https://sunli-lisun.github.io/ac221/data-sources.html · The 2025 system change (new system from August 2025; most in-scope types moved by mid-2026) and field renames: https://cdn.jsdelivr.net/gh/sgarcese/Civic-Analytics-Agent-Workflow-Claude-Skill@main/SKILL.md · CRM Value Codex (dataset page): https://data.boston.gov/dataset/311-service-requests · placeholder coordinates example: https://course.ccs.neu.edu/ds2500sp23/proposals/27.html
- **Street segments and addresses:** https://data.boston.gov/dataset/boston-street-segments-sam-system · https://data.boston.gov/dataset/fc9562ca-02df-40bf-b4db-a36effb52ccc
- **Neighbor:** Boston Globe pothole tracker: https://apps.bostonglobe.com/metro/2024/02/boston-potholes-tracker
- **CityScore dataset:** https://data.boston.gov/dataset/cityscore
- **Neighbors:** RentSmart: https://data.boston.gov/dataset/rentsmart · StreetSmart: https://streetsmart.inc/bos/guide · Augrented: https://augrented.com/
- **Kiro workflows:** https://kiro.dev/blog/introducing-workflows/ · https://kiro.dev/changelog/web/introducing-workflows/ · timeline: https://www.everydev.ai/developers/kiro
- **Kiro Crew:** https://infoq.com/news/2026/08/kiro-crew-coding-agents · https://chatgate.ai/post/kiro-crew
- **Custom agents:** https://kiro.dev/docs/custom-agents/
- **Street Bump:** https://d3.harvard.edu/platform-digit/submission/street-bump-crowdsourcing-better-streets-but-many-roadblocks-remain/index.html · https://boston.gov/transportation/street-bump · https://www.iol.co.za/business-report/economy/new-smartphone-app-to-report-potholes-automatically-1346550
