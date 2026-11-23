The Undead 311
==============

The Undead 311 finds Boston 311 requests that the city marked "closed" and that someone reported again at the same place within 60 days. It calls these possible zombies, shows them on a map with an evidence card for each, and puts a durability rate (stayed fixed) beside the city's speed rate (closed on time).

*Kiroween 2026, Frankenstein category. Independent project, not affiliated with the City of Boston.*

**Live site:** <https://undead311.netlify.app> (frozen on the judging snapshot, data through 2026-11-19)

## The 60-second judge path

No login. Open the site and press **Start the 60-second tour** in the top bar, or go straight to <https://undead311.netlify.app/judge>.

- The tour shows three possible zombies, about 20 seconds each. Space pauses, the right and left arrows move between them, Escape skips.
- All three come from the records check below: the city's own records show each re-report was closed as repaired again. The Skeptic agent recorded no objection to any of them.
- With reduced motion turned on in your system settings, the tour does not advance by itself. Use the next button.
- After the tour, open **Scorecard** for on time versus stayed fixed, **Methods** for definitions and limits, and **Check my street** to look up your own block.

The tour is frozen on the judging snapshot (`judged-2026-11-19-final`, run `snap-1120`). Its file list and hashes are in [data/SNAPSHOT.md](data/SNAPSHOT.md).

## Key results

Numbers are from the judging snapshot: 3,134,123 normalized cases from 2015 to 2026-11-19, of which 388,855 are in scope (persistent physical defects in the public right of way: potholes, sidewalks, streetlights, traffic signals, signs, pavement markings, street fixtures). Source: [`status.json`](https://undead311.netlify.app/data/status.json).

**Possible zombies: 19,077 in the headline, and that is a floor.** A zombie only appears if someone reports the problem again, so the count misses every problem that came back unreported. Four other groups are counted apart and left out of the headline:

| Group | Count | Why it is outside the headline |
|---|---|---|
| City re-reports | 32,855 | Opened by city crews or systems, often within an hour of the closure (13,298 of them), so they look like work records |
| Source unknown | 98 | New-system re-reports after a made-safe, referred or planned-follow-up closure; the new system does not say who opened a case |
| Sensitivity | 216 | Case types whose scope is uncertain |
| Planned follow-ups | 5,034 | Not zombies at all: the city scheduled the return visit |

**Closed on time versus stayed fixed** (headline tier, 309,590 eligible closed cases, 95% intervals from [`scorecard.json`](https://undead311.netlify.app/data/stats/scorecard.json)):

| Case type | Closed on time | Stayed fixed (raw) |
|---|---|---|
| Citywide | 65.8% (65.7% to 66.0%) | 61.4% (61.2% to 61.5%) |
| Potholes and roadway defects | 69.3% (69.1% to 69.6%) | 63.9% (63.6% to 64.2%) |
| Traffic signals | 95.3% (94.6% to 96.0%) | 78.2% (76.8% to 79.5%) |

Traffic signals show the widest gap, 17 points: 95.3% closed on time against 78.2% stayed fixed. The raw stayed-fixed rate counts only cases nobody reported again, so it is an upper bound on how many fixes held. If city re-reports are counted as re-reports, the citywide stayed-fixed rate falls to 51.8% (51.6% to 51.9%).

**Records check, 50 sites (seed 311).** No one visited the streets. For each of 50 sampled possible zombies in South End, Roxbury, Mission Hill and Fenway, we read how the city's records say the re-report was closed. Ten of 50 were closed as repaired again with no ambiguity: **20.0%, 95% interval 11.2% to 33.0%**. If the 11 ambiguous repairs also count, the share is up to 42.0% (29.4% to 55.8%). Eleven re-reports were still open, and 10 closed with text we could not classify. By case type the groups are small: streetlights 9 of 18, potholes 1 of 23. Method, rules and the full ambiguous list: [docs/VALIDATION.md](docs/VALIDATION.md).

**Coroner labels.** The Coroner agent labels closure text (resolved, noted, referred, made safe temporary, and so on). On 200 random closures it agrees with the pipeline's labels on 92.0% (184 of 200), 95% interval 87.4% to 95.0%.

## Limits

- **The baseline failed its placebo check, so the site does not show an excess count.** We ran the same estimator on closures moved to random other dates. A sound baseline would give an excess near 0. It gave -3,384 (95% interval -3,570 to -3,200), so the baseline over-expects coincidences and any "excess resurrections" figure built on it would be unreliable. By the rule fixed beforehand, we did not tune it further. The site shows the placebo result on the Methods page and withholds the excess and the adjusted stayed-fixed rate. See [docs/METHODS.md](docs/METHODS.md).
- **Counts are a floor.** Problems in places where people report less are undercounted. Do not rank neighborhoods by zombie counts without the reporting-intensity context on the Methods page.
- **The records check is not field validation.** It measures what crews wrote when they closed the re-report. A closure recorded as a repair can still be wrong. One reader classified the 50 closures by rules fixed before reading any of them; there is no second rater, and the sample covers four neighborhoods, not the city.
- **A possible zombie is not proof.** It might be the old problem coming back or a new one nearby. Only 67 of the 52,246 possible zombies in all groups carry a Skeptic objection, so the Second opinion section on a card is usually empty.
- **The new system hides who opened a case.** That is why the `source_unknown` group exists.
- **Agent permissions are not enforced in Kiro Web.** The nine custom agents in [.kiro/agents](.kiro/agents) declare read and write allowlists, but Kiro Web does not enforce them, and `.kiroignore` is honored only in the IDE. The `guard` and `kill-switch` hooks are a second layer, and one session had hooks that did not load at all ([docs/LEARNINGS.md](docs/LEARNINGS.md)). We treated the allowlists as documentation of intent and relied on review, CI and a hand-written answer key instead.

## How Kiro built it

Nearly all code was written in Kiro Web by Kiro agents, with the owner making the scope and method decisions. The evidence is in the repository:

- **Specs** ([.kiro/specs](.kiro/specs)): four, each with requirements, design and tasks: [zombie-engine](.kiro/specs/zombie-engine), [durability-stats](.kiro/specs/durability-stats), [haunted-web](.kiro/specs/haunted-web) and [nightly-and-deploy](.kiro/specs/nightly-and-deploy). Code docstrings and test names cite requirement IDs; `make trace` builds the requirement-to-test table.
- **Steering** ([.kiro/steering](.kiro/steering)): 14 files. [zombie-definition.md](.kiro/steering/zombie-definition.md) is the single source for every detection rule and parameter, with a dated change log. Changes made after seeing counts are logged there with the reason.
- **Custom agents** ([.kiro/agents](.kiro/agents)): nine. Coroner (labels closure text), Skeptic (argues each zombie is a coincidence), Data steward, Cartographer, Herald, two reviewers (stats and UX), and two implementers (engine and web).
- **Hooks** ([.kiro/hooks](.kiro/hooks)): nine files. A guard that blocks writes to protected paths such as the answer key, a kill switch, copy-lint on save, a Coroner re-check on label changes, and a hook that writes a line to the Kiro log at the end of a turn.
- **Workflows** ([.kiro/workflows](.kiro/workflows)): [build-undead-311](.kiro/workflows/build-undead-311.workflow.yaml) (layered build with test gates and cross-model review), [fulldata](.kiro/workflows/fulldata.workflow.yaml) (resumable full-data run) and [smoke](.kiro/workflows/smoke.workflow.yaml). Run reports are in [.kiro/workflow-runs](.kiro/workflow-runs), for example [build-4](.kiro/workflow-runs/build-4/report.md).
- **MCP servers** ([.kiro/settings/mcp.json](.kiro/settings/mcp.json)): five, including DuckDB (read-only queries over the processed data) and CKAN (finding the Analyze Boston files).
- **Property-based tests**: Hypothesis tests in [pipeline/tests/property](pipeline/tests/property) and fast-check tests in `web/src`, covering the 20 properties listed in [testing.md](.kiro/steering/testing.md). The detector must also reproduce a hand-worked answer key for a 75-case test town in 19 scenarios: [pipeline/tests/fixtures](pipeline/tests/fixtures). The rule is that the owner works out `expected_zombies.json` by hand ([worksheet](docs/TEST_TOWN_WORKSHEET.md)) and the guard hook stops agents editing it.
- **CI as the judge** ([.github/workflows/ci.yml](.github/workflows/ci.yml)): tests, the golden check, schema validation, copy-lint, an axe accessibility scan of judge mode, a 3 MB first-view budget, and pip-audit and npm audit.

The running log, one line per session including what Kiro got wrong and how it was fixed, is [docs/KIRO_LOG.md](docs/KIRO_LOG.md). Three entries worth reading: the kickoff run labeled new-system timestamps as UTC when they are Boston wall-clock time, shifting the sample by 4 or 5 hours (caught by comparing 1,373 re-created cases); a log hook wrote a wrong "673 files changed" line during a data copy; and the first full-data run reported a headline excess of -32,944 before each tier got its own baseline. Decisions with their evidence are in [docs/DECISIONS.md](docs/DECISIONS.md).

## Run it locally

You need [uv](https://docs.astral.sh/uv/) (Python 3.11, pinned in `.python-version`) and Node 22 (`.nvmrc`).

```
make setup           # install Python and Node dependencies
make pipeline-sample # run the pipeline on data/sample, no network needed
make web             # dev server for the site
make test            # Python and TypeScript tests, including property tests
make build           # production build into web/dist
```

The committed `web/public/data` is a sample export, so a fresh checkout shows sample numbers, not the figures above. To reproduce the full run, `make data-download` fetches the raw files into `$DATA_DIR` (it falls back to `.local-data/` in the repo, which git ignores), then `make pipeline` runs ingest, detection, statistics and export. Raw data is never committed. Check a frozen snapshot with `make snapshot-verify`. Deploy steps are in [docs/DEPLOY.md](docs/DEPLOY.md).

## Other cities

The detector, statistics and web app need only a normalized case table, a street-segment file and a closure-text label table. The Boston-specific parts are the ingest layer, the case-type crosswalk and the label tables. [docs/PORTING.md](docs/PORTING.md) lists each piece, what a new city must supply with effort estimates, and a worked mapping of New York City's published 311 schema.

## Data and licenses

- Boston 311 Service Requests, Boston Street Segments (SAM) and neighborhood boundaries, from [Analyze Boston](https://data.boston.gov), under the Open Data Commons Public Domain Dedication and License (PDDL).
- Map data (c) OpenStreetMap contributors, available under the Open Database License. No outside service is called at runtime.
- Fonts: Public Sans and Courier Prime, both under the SIL Open Font License, self-hosted.
- Code: MIT, see [LICENSE](LICENSE).

## Disclosure

Planning documents, starter steering files, prompts, and two setup scripts (`scripts/preflight_check.py`, `scripts/collect_github_settings.sh`) were drafted with an AI assistant (Claude) before implementation; all code was built with Kiro during the submission period. Pre-existing code: open-source frameworks and libraries only. Built by Kealoha Comcowich, an industrial engineering student at Northeastern.

Full plan: [docs/PROJECT.md](docs/PROJECT.md). Where each judging criterion is shown: [docs/CRITERIA_MAP.md](docs/CRITERIA_MAP.md).
