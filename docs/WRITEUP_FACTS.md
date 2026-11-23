# Write-up facts

Facts only, for the person writing the prose. Every number has a source in the "Source" column or in the line under the table. Nothing here is interpretation, except the two lists at the end (limits and three moments), which are my selection from the record and are marked as such.

How this sheet was built, 2026-11-23: repo at `main` 639c10f (398 commits); GitHub REST reads of `ShroudedArrow/undead-311`, `ShroudedArrow/undead-311-ops` (the agent channel) and `ShroudedArrow/undead-311-data`; and the final snapshot archive `exports-snap-1120.tar.gz` from the `exports-snap-1120` release of `undead-311-data`, downloaded and checked against the sha256 in `docs/DECISIONS.md` (d67dfbf069007806342230ca36c81a5bfbe28340e577387da6c54e13f0fe4106). Test counts are collected counts from this checkout, not a fresh pass/fail run (see "Tests").

"snap-1120" is the judging snapshot: data through 2026-11-19, data version `2026-11-20+27ceb33+89e078da`.

## 1. Headline numbers (snap-1120)

| Fact | Value | Source |
|---|---|---|
| Legacy raw rows | 3,040,547 | `status.json` `row_counts.raw_legacy` |
| New-system raw rows | 93,576 | `status.json` `row_counts.raw_new` |
| In-scope cases after cleaning | 388,855 | `status.json` `row_counts.in_scope_cases` |
| Possible zombies, all tiers | 52,246 | `stats/scorecard.json` `counts` (sum of the four tiers below); also the number of card records in `cards/*.json` |
| Headline tier | 19,077 | `status.json` `headline_count` |
| City re-report tier (outside headline) | 32,855 | `status.json` `city_rereport_count` |
| Source-unknown tier (outside headline) | 98 | `status.json` `source_unknown_count` |
| Sensitivity tier (outside headline) | 216 | `status.json` `sensitivity_count` |
| City re-reports opened under 1 hour after the closure | 13,298 | `status.json` `city_rereport_under_1h_count` |
| City re-reports as share of headline plus city | 63% (32,855 of 51,932) | `status.json` `anomalies` |
| Planned follow-ups (not zombies) | 5,034 | `status.json` `planned_followup_count` |
| Separate deaths (invalid or duplicate originals) | 7,821 | `separate_deaths.json` |
| Cross-system mirror copies merged | 36 | `status.json` `mirror_copies_merged` |
| Bulk-closure groups and cases | 127 groups, 10,442 cases | `status.json` `row_counts` |
| Repeat-offender chains | 547 | `repeat_offenders.json` |
| Match mode, headline tier | segment 10,783; radius 7,527; intersection 767 | `stats/excess.json` `match_modes` |
| Snapped / unsnapped in-scope cases | 233,909 / 154,946 | `status.json` `row_counts` |
| SAM intersections derived from segment geometry | 11,802 | `status.json` `row_counts.intersections`; derivation in `docs/DECISIONS.md` 2026-11-13 (19,442 segments, 13,828 distinct endpoints, 85% shared by two or more) |
| Excluded: type out of scope / unlisted type | 862,905 / 1,879,450 | `exclusions.json` `counts` |
| Excluded: no coordinates / placeholder points / test data | 2,120 / 792 / 1 | `exclusions.json` `counts` |
| On-time rate, citywide | 65.85% (95% 65.68 to 66.02), n 310,101 | `stats/scorecard.json`, family citywide, tier_set all |
| Stayed-fixed rate (raw), headline tier | 61.36% (95% 61.19 to 61.54), n 309,590 | same file, tier_set headline |
| Stayed-fixed rate (raw), all tiers | 51.77% (95% 51.59 to 51.94), n 310,101 | same file, tier_set all |
| Adjusted stayed-fixed rate | not exported (`stayed_fixed_adj` is null) | `scorecard.json`; `docs/DECISIONS.md` 2026-11-17 |
| Share still holding at 7 / 30 / 90 days (citywide, 365-day horizon) | 97.95% / 95.38% / 91.99% | `stats/survival.json`, curve `all`; 288,776 originals, 42,537 events; half-life is null (the curve never reaches 0.5) |
| Zombies with a Skeptic objection | 67 of 52,246 (50 weakened, 9 explained away, 8 survives); the other 52,179 are `not_reviewed` | `cards/*.json` `skeptic_verdict` |
| Judge tour | 3 zombies, `confirmation: records`, `provisional: false`, ranked by most re-reports | `stats/judge_tour.json` |
| First view, gzip (status, points, scorecard, judge tour) | 326,240 bytes against a 3,000,000 byte budget | my computation from the archive, zlib level 6 as in `docs/METHODS.md` "Payload budget" |
| Closure notes hidden by the 5-case rule | 23,672 of 104,492 card case records carry `closure_text_hidden` | `cards/*.json`; the flag may also be set for records with no usable text (not checked) |

The archive's run report (`processed/run_report.json`) is not in git or in the release, so counts that only it holds (per-stage timings, Coroner coverage for snap-1120) are not on this sheet. Coroner coverage below is from run full-3.

## 2. Pull requests

45 pull requests in `ShroudedArrow/undead-311`, 2026-11-12 to 2026-11-23. 42 merged, 3 closed without merging (#14, #15, #21). Opened by `kiro-agent[bot]`: 34; by `ShroudedArrow`: 11. Source: `gh api repos/ShroudedArrow/undead-311/pulls?state=all`.

Commits on `main`: 398. Authors: "Kiro Agent" 336, ShroudedArrow 61, "Kiro" 1 (`git log --format=%an`). Commits with a `Kiro-Agent` trailer: 311 (`git log --format=%B`). Trailer values: engine 175, web 107, kiro 14, orchestrator 7, manual 4, skeptic 1, setup 1, data-steward 1, coroner 1. `Kiro-Run` values: build-1 117, manual 79, build-3 62, build-2 29, build-4 20, full-1 3, snap-1120 1.

| PR | Merged | Title |
|---|---|---|
| 1 | 2026-11-12 | Starter kit and pre-registered zombie definition |
| 2 | 2026-11-12 | Gate 1 setup: OWNER placeholder and plan-freeze entry |
| 3 | 2026-11-12 | chore(kickoff): verify 311 data, record go/no-go, add sample |
| 4 | 2026-11-13 | Gate 2: agents, hooks, test-town cases, workflows |
| 5 | 2026-11-13 | Specs 1, 2, 3, 5 |
| 6 | 2026-11-13 | Gate 2 follow-ups |
| 7 | 2026-11-13 | Hooks for cloud configuration |
| 8 | 2026-11-13 | fix(workflows): every repeat loop writes its own stop file |
| 9 | 2026-11-13 | Update channel-status.json |
| 10 | 2026-11-13 | docs: record disabling the channel-status hook; log smoke-3 |
| 11 | 2026-11-13 | Create expected_zombies.json |
| 12 | 2026-11-13 | Gate 3 readiness check (2026-11-13) |
| 13 | 2026-11-13 | Update zombie-definition.md |
| 14 | not merged | build-1: demo-critical + approved credibility (partial) |
| 15 | not merged | Update zombie-definition.md |
| 16 | 2026-11-14 | Update zombie-definition.md |
| 17 | 2026-11-14 | RE-SYNC NEEDED: build-2 decision batch, recipe inputs, cloud sync check |
| 18 | 2026-11-14 | Update methods.md |
| 19 | 2026-11-14 | Update methods.md |
| 20 | 2026-11-14 | feat(workflows): carry_from input; durability-stats credibility loop max 4 |
| 21 | not merged | build-3: demo-critical + credibility + delight (in progress) |
| 22 | 2026-11-15 | Update methods.md |
| 23 | 2026-11-16 | Build build-4: demo-critical, credibility, delight layers |
| 24 | 2026-11-16 | fix(pipeline): prepare the full-data run |
| 25 | 2026-11-17 | fix(fulldata-2): per-tier baselines, Coroner phrases, sharded exports, release publish |
| 26 | 2026-11-16 | Update methods.md |
| 27 | 2026-11-17 | docs(coroner): owner spot-check of 20 Coroner labels, 19 of 20 agree |
| 28 | 2026-11-17 | fix(text): Coroner Case Noted rule, staff-name scrub, 5-case rule for closure notes |
| 29 | 2026-11-17 | ci(netlify): skip production builds so main cannot overwrite the nightly deploy |
| 30 | 2026-11-17 | feat(copy): owner texts, Who made this section, Spanish hidden until reviewed |
| 31 | 2026-11-18 | fix: snapshot-ready (REST publish, finished-run guard, judging tag files, judging-final) |
| 32 | 2026-11-18 | fix(nightly): run repo scripts with uv run --locked; Node 24 actions; lazy duckdb import |
| 33 | 2026-11-19 | fix(nightly): draft deploy with smoke test, --no-build, share images for real targets only |
| 34 | 2026-11-19 | UI polish: code-drawn markers, fixed-height home, time-lapse focus, methods column |
| 35 | 2026-11-19 | fix(pii): remove first-name staff names in the middle of a note |
| 36 | 2026-11-19 | perf(web): collapsible footer note and a faster map |
| 37 | 2026-11-21 | fix(ops): make exports-release tests hermetic without DATA_DIR |
| 38 | 2026-11-20 | feat(snapshot): judging snapshot snap-1120 (judged-2026-11-20) |
| 39 | 2026-11-21 | fix(guard): block commands that print environment variables |
| 40 | 2026-11-21 | Records-based validation replaces field visits |
| 41 | 2026-11-21 | Update methods.md |
| 42 | 2026-11-23 | feat(ops): exports-only judging-final and final judging snapshot for snap-1120 |
| 43 | 2026-11-23 | Design: direction A with C touches, form pages, postmortem card, night map |
| 44 | 2026-11-23 | Update design-system.md |
| 45 | 2026-11-23 | docs(snapshot): final and provisional archive hashes for snap-1120 |

PR #14 is the build-1 result (title says "partial"), #21 is the build-3 result ("in progress"), both closed unmerged. Their work reached `main` through later PRs (`docs/KIRO_LOG.md` 2026-11-14 integrate entry). #15 is titled "Update zombie-definition.md" like #13 and #16 and was closed unmerged.

## 3. Workflow runs and review-loop passes

Recipe `build-undead-311` (`.kiro/workflows/build-undead-311.workflow.yaml`): three layers (demo-critical, credibility, delight), each with spec loops on an engine branch (zombie-engine, durability-stats, nightly-and-deploy) and a web branch (haunted-web) in parallel, then integrate steps, a design gate (max 3 passes), a preview, a preview review, a retro and a report. Loop maximum is 3 iterations, except `durability-stats-credibility-loop` which was raised to 5 and then set to 4 (`docs/DECISIONS.md` 2026-11-14; the YAML shows 4). Implementers and gates run `claude-sonnet-5.5`; all reviewers run `claude-opus-5.5` (`docs/DECISIONS.md` 2026-11-12, recipe `modelId` lines). Each loop is implement, deterministic validate gate (`scripts/validate_gate.py`), then a reviewer on the other model.

Runs recorded in the agent channel (`ShroudedArrow/undead-311-ops`, run-log issues):

| Run | Recipe | Issue | Comments on the run-log issue | Outcome (from the run log) |
|---|---|---|---|---|
| smoke-1 | channel test | ops#1 | n/a | closed |
| smoke-2026-11-12a | smoke, steps run by the session | ops#4 | n/a | gate PASS, review APPROVED, stop issue ops#5 halted the next step on purpose (`docs/DECISIONS.md` 2026-11-12) |
| smoke-2 | smoke | ops#6 | n/a | halted by stop issue ops#7 on purpose, run marked aborted (`docs/KIRO_LOG.md` 2026-11-13) |
| smoke-3 | smoke | ops#8 | n/a | passed end to end, gate PASS with 394 tests, review APPROVED |
| build-1 | build-undead-311 | ops#11 | 61 | demo-critical loops all approved; credibility loops approved except durability-stats, which ended on iteration 3 with CHANGES_REQUESTED. PR #14 |
| build-2 | build-undead-311 | ops#117 | 35 | FAILED: `durability-stats-credibility-loop` hit 5 of 5 iterations without approval, one blocker (ops#141) needed the owner |
| build-3 | build-undead-311 | ops#145 | 52 | FAILED: `haunted-web-delight-loop` ended at pass 3 of 3 without approval (ops#190); branches pushed |
| build-4 | build-undead-311 | ops#195 | 28 | all loops APPROVED and PASS, design gate passed on pass 2, preview review CHANGES_REQUESTED (UX-65 blocking). PR #23, merged 2026-11-16 after manual fixes (`.kiro/workflow-runs/build-4/report.md`) |
| full-1 | full-data pipeline | ops#222 | 42 | first full-data run |
| rehearsal-1 | fulldata | ops#224 | 75 | second pass was a killed leg (`docs/DECISIONS.md` 2026-11-18) |
| rehearsal-2 | fulldata | ops#225 | 46 | |
| snap-1120 | fulldata | ops#229 | 56 | produced the judging snapshot |

Count: 12 run-log issues (4 smoke or channel-test runs, 4 build runs, 4 full-data runs). Four runs of the `build-undead-311` recipe. Comment counts from `gh api repos/ShroudedArrow/undead-311-ops/issues/<n>/comments`.

Reviewer verdicts per loop, counted from reviewer comments in each run-log issue (keyword match on APPROVED and CHANGES_REQUESTED in the first 500 characters of the summary). A pass whose comment was not posted is missed: build-4's design gate shows 1 verdict comment here but 2 passes in `report.md`.

| Run | Loop | Verdicts in order |
|---|---|---|
| build-1 | haunted-web demo-critical | CR, CR, A |
| build-1 | zombie-engine demo-critical | CR, A |
| build-1 | durability-stats demo-critical | CR, A |
| build-1 | nightly-and-deploy demo-critical | CR, A |
| build-1 | haunted-web credibility | CR, CR, A |
| build-1 | zombie-engine credibility | CR, CR, A |
| build-1 | durability-stats credibility | CR, CR, CR (no approval) |
| build-2 | haunted-web credibility | A |
| build-2 | zombie-engine credibility | CR, A |
| build-2 | durability-stats credibility | CR, CR, CR, CR, CR (no approval) |
| build-3 | haunted-web credibility | CR, A |
| build-3 | durability-stats credibility | CR, A |
| build-3 | nightly-and-deploy credibility | CR, A |
| build-3 | zombie-engine delight | CR, CR, A |
| build-3 | haunted-web delight | CR, CR, CR (no approval) |
| build-4 | durability-stats delight | A |
| build-4 | haunted-web delight | CR, A |
| build-4 | nightly-and-deploy delight | CR, A |
| build-4 | design gate | A (report.md: CR then A) |
| build-4 | preview review | CR (single pass, no loop) |

CR is CHANGES_REQUESTED, A is APPROVED. Totals: 45 verdict comments, 29 CR and 16 A (build-1 18, build-2 8, build-3 12, build-4 7). Source for build-4's own table: `.kiro/workflow-runs/build-4/report.md` (loops 1, 2, 2, 2 passes; 18 of 18 commits carry both trailers; no "Interrupted by agent restart").

Agent-channel totals (`ShroudedArrow/undead-311-ops`, issue numbers 1 to 231, no PRs): 231 issues, 196 closed, 35 open. Labels: `type:finding` 178 (162 closed, 16 open), `type:proposal` 24 (22 closed), `type:status` 16, `type:decision` 6, `type:handoff` 7, `type:question` 1, `needs-human` 17 (9 closed), `stop` 2 (both closed), `to:engine` 127, `to:web` 80, `to:human` 11, `to:reviewer-stats` 2, `to:reviewer-ux` 1. An issue can carry several labels.

Full-data runs: first run full-1 (2026-11-16), then full-2 and full-3 (fix/fulldata-2, `reports/full-2`, `reports/full-3`), rehearsal-1 and -2 (2026-11-18), snap-1120 (2026-11-20).

## 4. Agents and what each did

Nine custom agents in `.kiro/agents/` (tools: read, write, shell, `@github-channel`; reviewer-ux also `@playwright`; herald has no shell). Evidence of work is from commit trailers, channel labels and `docs/KIRO_LOG.md`.

| Agent | Role (from its definition) | What the record shows |
|---|---|---|
| engine | Implements the Python pipeline, owns `pipeline/` and `schemas/` | 175 commits with `Kiro-Agent: engine`. Detector, SAM snapping, baseline, shift test and placebo, exports, nightly template, `make capture` |
| web | Implements the Vite + React app, owns `web/` | 107 commits with `Kiro-Agent: web`. Map, table, autopsy card, scorecard, judge tour, methods page, charts, a11y and e2e tests |
| reviewer-stats | Read-only review of `stats/` and `detect/` against methods.md and zombie-definition.md | No commits. Filed findings to `to:engine` (127 issues carry that label); verdicts above. Reviews nightly-and-deploy loops too (recipe) |
| reviewer-ux | Read-only review of the web app through Playwright | No commits. Filed findings to `to:web` (80 issues); also the design review of 2026-11-22 (`docs/DESIGN_REVIEW.md`: 15 ranked suggestions, three direction mocks) and four rounds of review of branch `ui/polish` (round 4 approved) |
| coroner | Labels closure-text templates with one allowed label | 1 commit (3958d1b): 3,926 templates, covering 95% of in-scope closed cases at that date. Current table `data/labels/coroner_labels.csv` has 3,915 rows |
| skeptic | Argues each zombie is a coincidence | 1 commit (372c6d4): objections for the 200 top-report headline zombies, from the sample run (`data/labels/skeptic_objections.json`, 200 objections, run build-1) |
| data-steward | Validates data files, proposes data-dictionary changes | 1 commit (kickoff, 6434e15: verified data, go/no-go, sample). Cannot edit steering (guard), writes proposals instead (`docs/DECISIONS.md` 2026-11-12) |
| cartographer | Builds and size-checks map data files | No commit trailer, no log entry, no channel label found |
| herald | Writes the weekly Resurrection Report | No commit trailer, no log entry, no channel label found |

Other `Kiro-Agent` values: `kiro` 14 and `orchestrator` 7 (session and workflow orchestration), `manual` 4, `setup` 1.

Also in `.kiro/`: 4 specs, 14 steering files, 3 workflow recipes, 9 hook files, MCP servers `context7`, `duckdb`, `ckan`, `playwright`, `github-channel` (`.kiro/settings/mcp.json`). The counts line at the top of `docs/KIRO_LOG.md` says 0 powers and dates from 2026-11-12.

`docs/KIRO_LOG.md`: 107 entries, 6 of them auto-written by the kiro-log hook ("N files changed"). `docs/LEARNINGS.md`: 92 one-line entries. `docs/DECISIONS.md`: 94 dated rows.

## 5. Hooks and what the guard blocked

Nine hook files, ten hook definitions (`.kiro/hooks/*.json`):

| Hook | Trigger | State | What it does |
|---|---|---|---|
| guard | PreToolUse, every call | enabled | `scripts/guard.py` classifies the tool. Shell: blocks `rm -rf` in the repo or DATA_DIR, force pushes, `git reset --hard`, `git clean -f`, remote branch deletion, `+refspec` pushes, shell edits of protected paths, and (since 2026-11-21) commands that print environment variables. File writes: blocks `.kiro/steering|settings|hooks|agents/**`, `.kiro/STOP` and `pipeline/tests/fixtures/expected_zombies.json`. Allows `.kiro/workflow-runs/**` and tasks.md checkbox changes |
| kill-switch-task | PreTaskExec | enabled | Blocks the next task if `.kiro/STOP` exists or the channel has an open `stop` issue; fails open if GitHub is unreachable. PreTaskExec does not fire in Kiro Web |
| kill-switch-tool | PreToolUse | enabled | The same check on shell and file-write tools, which is the one that fires in Kiro Web |
| kiro-log | Stop | enabled | Appends a changed-files line to `docs/KIRO_LOG.md` (a command, spends no credits) |
| coroner-eval | PostFileSave on `data/labels/coroner_labels.csv` | enabled | Coroner accuracy check |
| detector-revalidate | PostFileSave on `pipeline/undead311/detect/` | enabled | Re-scores the validation sample |
| channel-status | PostTaskExec | disabled by the owner (PR #9, 2026-11-13) | Posted a status comment per task; it duplicated and misnamed steps |
| test-on-save, copy-lint | PostFileSave | disabled (the workflow gates run them) | |
| data-validate | PostFileCreate on `data/raw/` | disabled (an agent hook, spends credits) | |

Hook payload tests: 107 payload cases at the 2026-11-13 entry (`docs/KIRO_LOG.md`); `pipeline/tests/unit/test_hooks.py` has 49 test functions today (parametrized cases not counted).

The guard keeps no block counter. The blocks that are written down:

| Date | What was blocked | Source |
|---|---|---|
| 2026-11-13 | Kiro editing `.kiro/hooks/` (the channel-status disable); the owner made the edit | `docs/KIRO_LOG.md` |
| 2026-11-13 | A tool call whose inline script mentioned the answer key; the tests were rewritten with the file-write tool | `docs/KIRO_LOG.md` build-1 setup |
| 2026-11-14 | Editing `.kiro/agents/engine.json` (ownership change left for the owner) | `docs/KIRO_LOG.md` |
| 2026-11-12 onward | Inline shell scripts naming a protected path, `rm -rf` inside the repo or DATA_DIR, forced `git clean` | `docs/LEARNINGS.md` lines 21, 61, 64 |
| 2026-11-21 | Rule added after two transcripts printed sandbox secrets: `env`, `printenv`, bare `set`/`export`, `ps e`, `pgrep -a`, `/proc/*/environ`, also inside `sh -c`, `$(...)`, `xargs`, `sudo`. The first version of the rule blocked Kiro's own log-line command (backticks inside single quotes); both caught by running it | `docs/LEARNINGS.md` line 94, `docs/KIRO_LOG.md` 2026-11-21, PR #39 |
| 2026-11-12 | Not a block: the live probe `git push --force --dry-run` was NOT blocked in the first session, because the repo hooks were not loaded there and the matcher `shell` would also have missed `execute_bash`. Hooks were rewritten to run on every tool call | `docs/KIRO_LOG.md` 2026-11-13 |

`pipeline/tests/fixtures/expected_zombies.json`: one commit (b8db3a4, 2026-11-13, by the owner, PR #11), never edited after. The test town has 75 cases in 19 scenarios (`docs/KIRO_LOG.md` 2026-11-12); the detector reproduced it with 20 zombies at build-1.

## 6. Specs, requirements and tests

| Spec | Requirement headings | EARS criteria lines | demo-critical / credibility / delight | Task lines | Ticked |
|---|---|---|---|---|---|
| zombie-engine | 34 | 93 | 23 / 10 / 1 | 52 | 52 |
| durability-stats | 23 | 38 | 4 / 17 / 2 | 32 | 31 (task 19, before/after export, descoped by owner decision 5, ops#170) |
| haunted-web | 23 | 53 | 12 / 4 / 7 | 31 | 31 |
| nightly-and-deploy | 13 | 20 | 2 / 9 / 2 | 15 | 15 |
| Total | 93 | 204 | 41 / 40 / 12 | 130 | 129 |

Source: `.kiro/specs/*/requirements.md` (count of `### REQ` headings; criteria counted as numbered lines starting with WHEN, IF, WHILE, THE or WHERE, so the criteria column is a floor) and `tasks.md` (count of checkbox lines). The 2026-11-12 log entry recorded 82 requirements and 81 tasks when the specs were first written; the specs grew during the build.

Correctness properties in the design files: zombie-engine P1 to P22, durability-stats P1 to P10, haunted-web W1 to W8 (table rows in each `design.md`), plus nightly-and-deploy checks O1 to O5 that are structural, not property-based. The log also cites W9 and P10b, added during the build.

Tests, collected today from this checkout with the locked dependencies (`uv run --locked pytest pipeline/tests --collect-only`, `npx vitest list`). These are collected counts, not a run result.

| Suite | Count |
|---|---|
| pytest, all | 1,829 collected, in 96 files under `pipeline/tests` |
| pytest, `pipeline/tests/property/` | 80 collected, in 17 files |
| `@given` decorators in `pipeline/tests` | 84 |
| vitest | 475 listed |
| fast-check, `fc.assert` calls in `web/src` | 54, across 19 files that use fast-check |
| Latest recorded e2e and axe (build-4, `report.md`) | 43 passed, 1 phone-only skip; axe 0 violations, 0 third-party requests |
| Latest recorded counts at build-4 design-fix | 1,299 pytest, 408 vitest |
| Test requirement citations | 273 distinct `REQ-` IDs appear in `pipeline/tests` and `web/src`, across 330 files |

Repo size: 1,429 tracked files; 66 Python modules in `pipeline/undead311`; 160 TypeScript files in `web/src`; 22 files in `schemas/`.

Lint today: `ruff check pipeline` passes; `ruff check .` reports 36 errors (17 fixable), in `scripts/` and `ops/` (23 at the build-4 report). `make lint`, the gate, only covers the pipeline and web.

CI on `ShroudedArrow/undead-311` (81 recorded runs, `gh api .../actions/runs`): `ci` 58 success, 8 failure, 7 cancelled; `deep-pbt` 4 success, 3 failure, 1 in progress. `ci` jobs: python, web, copy-lint, axe, budget, audit, channel. `ci` on `main` at 639c10f: success. The channel issue ops#231 ("[alert] CI failed on main", main@9dd0733, 2026-11-21) is still open although later runs pass.

## 7. Statistical corrections made along the way

Baseline estimator, build-1 to build-3 (reviewer-stats findings, fixed by engine):

| Step | What was wrong | Number | Source |
|---|---|---|---|
| First estimator | Share of windows with a report ran high at sparse spots | 40% high | `docs/KIRO_LOG.md` 2026-11-14 loop 3; `docs/DECISIONS.md` 2026-11-14 |
| Chains | When a re-report's own closure started no dead stretch, the next link counted as a chance report | expected count 50% above true chance on a town with causal re-reports; 18 to 20% above after the fix | `docs/METHODS.md` "Same-spot baseline" (ops#113) |
| Seasonal bias | Replacement estimator was biased by season | spot baseline 9% high on a null town with a busier winter | build-1 run log, reviewer comment, iteration 3 |
| Hybrid | Sparse spots use the season-integrated estimator, dense spots use a sliding-window share, one function shared by excess and placebo | 40 seeded null-town tests; null-town tables in `docs/METHODS.md` | ops#130, #131, #132 |
| Reports-stop towns | Remaining bias documented as a limit, estimator not changed before the owner answered | 12 rows and a pinning test | ops#141, #142 |
| Burstiness flag | The literal concentration test flagged almost every sparse spot | 281 to 293 of 300 flagged; after the owner's 8-report minimum and half-expected-months rule, the sparse null town flags 0 of 296 and 0 of 297 | `docs/KIRO_LOG.md` 2026-11-15; `docs/METHODS.md` |

Baseline population and match area, the full-data runs (headline tier):

| Run | Change | Headline excess | Headline placebo | Source |
|---|---|---|---|---|
| full-1 | One expected count for every same-family report, city crew reports included | -32,944 | -8,528 | `docs/METHODS.md` "Baseline population per tier" |
| full-2 | Per-tier baseline populations: each tier counts only the reports its re-reports can come from | -9,839 | -3,152 (excludes 0) | same; `docs/KIRO_LOG.md` 2026-11-16 |
| full-3 | Spot is the original's own match area, not the whole segment or 60 m cell; source-unknown cohort limited to originals whose window reaches the new system (35,835 down to 2,539 originals; expected count 11,271 down to 865) | -4,928 (-5,377 to -4,486); 18,904 observed, 23,832 expected, 251,583 originals | -3,322 (-3,504 to -3,110) (excludes 0) | `reports/full-3/STATS_REVIEW.md` |
| snap-1120 | Same method as full-3 on data through 2026-11-19 | -4,939 (-5,376 to -4,525); 18,857 observed, 23,796 expected, 251,240 originals | -3,384 (-3,570 to -3,200) (excludes 0) | `stats/excess.json` rows `kind: tier`, `by_tier`, `placebo` |

Other numbers on this thread: weighting the spot's reports by the share within the match distance cut the headline cohort's expected count by 17% (`docs/LEARNINGS.md` 2026-11-16); pooled-rate fallbacks rose from 34,463 to 48,079 headline originals when areas replaced whole segments (`reports/full-3/STATS_REVIEW.md`); the shift test's observed count for snap-1120 is 20,360 against a shifted mean of 14,749 (2.5% to 97.5%: 14,435 to 15,047, 1,000 runs, seed 311); the city re-report tier excess is +12,534 (11,602 to 13,457), 12,116 of it in the 0 to 5 m band in the full-3 run, which the review attributes to crew work records filed right after closures.

Placebo decision (rule fixed before the run, `.kiro/steering/methods.md`; owner answer 2026-11-16 in `docs/DECISIONS.md`): if the headline placebo interval does not cover 0, no further tuning, the excess is shown nowhere on the site, and the methods page shows the placebo instead. On full-3 and on snap-1120 the interval excludes 0, so the excess is withheld. `reports/full-3/STATS_REVIEW.md` records: "I did not tune anything after seeing this." Consequences on 2026-11-17 (owner decision): adjusted stayed-fixed rate removed from every export; confidence score kept for ranking only, because its chance term comes from the same uncalibrated baseline. `status.json` carries `calibration_warning`: "placebo excess -3384.0 (95% interval -3570.2 to -3200.2) excludes 0". Two explanations remain, not separated by a test: one report falls in several originals' overlapping match areas (median 5 cases, 95th percentile 36) but is attached to one incident; and the dense-spot estimator is cautious.

Detection-side corrections that changed counts:

| Change | Number | Source |
|---|---|---|
| New-system timestamps were mislabeled UTC at kickoff; they are Boston wall-clock | 1,373 legacy cases closed "Resubmitted as / See new case BCS-N" were re-created in the new system; new open minus legacy close has median -2.6 min (p5 -14.7, p95 -1.1) in every month, where a true UTC offset would give 4 h or 5 h | `.kiro/steering/data-dictionary.md` "Time zones (corrected)" |
| Matching: snapped cases on different segments never match by radius; intersection exception | 15 m intersection radius; 11,802 intersections | `docs/DECISIONS.md` 2026-11-13 |
| Coroner labels moved the headline | 20,766 to 19,112 (accepted by the owner) | `docs/DECISIONS.md` 2026-11-16 (4) |
| City re-reports moved to their own tier before any full-data run | 65% of headline zombies in the sample were city-originated, many within an hour of closure | `.kiro/steering/zombie-definition.md` change log 2026-11-14 |
| Three high-frequency intersection points kept in the data | 224, 224 and 207 in-scope cases; 222 of 224, 222 of 224 and 202 of 207 share one intersection address; effect on zombie counts not measured | `docs/DECISIONS.md` 2026-11-20; `docs/METHODS.md` |
| Placeholder points dropped | 792 cases at 42.3603,-71.0583 and 42.3595,-71.0588 | `exclusions.json` |

## 8. Coroner coverage and accuracy

| Fact | Value | Source |
|---|---|---|
| Label table | 3,915 templates: resolved 1,831; referred 717; invalid 390; duplicate 373; noted 225; planned_followup 196; made_safe_temporary 138; other 27; bulk_backlog 18 | `data/labels/coroner_labels.csv` |
| Coverage of in-scope closed cases, full-3 | 99.52% (1,527 unlabeled of 315,606): legacy 99.80% (628 unlabeled of 306,674), new system 89.94% (899 unlabeled of 8,932) | `reports/full-3/coverage.json` |
| Coverage before the leading-phrase rule | 63.7% | `docs/KIRO_LOG.md` 2026-11-16 |
| Agreement with the Coroner agent on a random draw of 200 closures (seed 311) | 92.0% (184 of 200), Wilson 95% 87.4% to 95.0%; 0 left as `other` | `docs/VALIDATION.md` |
| Agreement by label source | table 126 of 128; leading phrase 58 of 70; closure code 0 of 2 | `docs/VALIDATION.md` |
| Largest confusion | referred labeled noted by the pipeline, 3 cases | `docs/VALIDATION.md` |
| Owner spot check of 20 rows from the 200 | 19 of 20 agree; row 3 ("Case Noted picked up sign") should be `made_safe_temporary` | `docs/CORONER_SPOTCHECK.md`; `docs/DECISIONS.md` 2026-11-17 |
| "Case Noted" closures labeled resolved before the fix | 2,980 of 34,623 (2,149 from the leading-phrase rule) | `docs/KIRO_LOG.md` 2026-11-17 |
| A first negation pattern matched every word ending in "nt" | moved 1,688 closures to `noted`; found by reading samples of the changes | `docs/KIRO_LOG.md` 2026-11-17 |

The 200-row set is labeled by the Coroner agent. No human hand-label set exists (`docs/DECISIONS.md` 2026-11-16 (3)). The owner's verdicts in the spot check were reviewed against suggested verdicts from Claude outside Kiro (same entry, 2026-11-17).

Records-based validation of the 50-site sample (seed 311), against the city's own records on 2026-11-21 (`docs/VALIDATION.md`, `docs/DECISIONS.md` 2026-11-21):

| Fact | Value |
|---|---|
| Repaired again, unambiguous | 20.0% (10 of 50), Wilson 95% 11.2% to 33.0% |
| Repaired again, ambiguous counted too | up to 42.0% (21 of 50), 29.4% to 55.8% |
| Among re-reports already closed | 25.6% (10 of 39), 14.6% to 41.1% |
| Classes | repaired again 21 (11 ambiguous), duplicate 2, invalid or nothing found 4, referred 2, still open 11, other 10 (all ambiguous) |
| By type | pothole roadway 1 of 23 (4.3%); sidewalk 0 of 5; sign 0 of 4; streetlight 9 of 18 (50.0%, 29.0% to 71.0%) |
| Status changes since the snapshot | none of the 50 |
| Classification rules | fixed in code before the 50 closures were read, not changed after |

## 9. Privacy scrubbing

| Fact | Value | Source |
|---|---|---|
| Surname check list | 37 surnames, human-made from names found in the data, not committed | `docs/METHODS.md` "Closure notes and staff names" |
| Closed cases naming one of them in the raw text | 18,966 | same |
| After the first scrub (sign-off, slash names, name beside a title) | 18,694, then 1,038 after all three patterns | same |
| After the run-time staff-name list and the 5-case rule | 80 (two surnames that are also street names) | same; accepted as a known limit 2026-11-17 |
| Staff-name list | 126 names, built from the full data at run time into `$DATA_DIR/staff_names.txt`, never committed | `docs/DECISIONS.md` 2026-11-17 |
| First-name list | 2,000 most common US first names (births 1950 to 2000, SSA public data, built from a GitHub mirror because ssa.gov returned 403) | `docs/METHODS.md`; `docs/KIRO_LOG.md` 2026-11-18 |
| 5-case rule | A closure note shows on a card only when its scrubbed, number-masked text is shared by at least 5 closed cases | `docs/DECISIONS.md` 2026-11-17 |
| Card case records with the note hidden | 23,672 of 104,492 | `cards/*.json`, see section 1 |
| Digit-run replacements in the sample after keeping case IDs | 165 down to 11 | `docs/KIRO_LOG.md` 2026-11-16 |
| Street names that lost a middle initial in the first rule | 1,930 address strings, fixed by keeping the initial before a street word | `docs/KIRO_LOG.md` 2026-11-18 |
| Repeat-offender chains shown at block level | 482 of 547 | `repeat_offenders.json` `block_level` |

## 10. Deploy pipeline

Hosting: Netlify free plan (owner decision 2026-11-13); GitHub Pages not used. Production URL: not recorded in the repo's docs. Judged repo `ShroudedArrow/undead-311` is public, MIT. The data repo `ShroudedArrow/undead-311-data` is private.

| Stage | Fact | Source |
|---|---|---|
| Full-data run | Resumable stages with done markers, run in legs under a 30-minute foreground cap; a killed leg once rebuilt all 16 stages (about 3 hours) before the fix | `docs/DECISIONS.md` 2026-11-18 |
| Export | Exports are plain JSON, no `.gz` twins; payload measured on gzip transfer size | `docs/DECISIONS.md` 2026-11-15; `docs/METHODS.md` |
| Publish | `exports_release.py publish` packs exports into a release asset with `MANIFEST.json` and a sha256; the REST upload is checked by downloading it again | `docs/DEPLOY.md`; PR #31 |
| Snapshot | `make snapshot` hashes 685 files (combined sha256 `ff22636c22d9abed898522e2a5c4c23d5d131c80ccf493b7facc285e89800ddd`); tag `judged-2026-11-20` (provisional) and `judged-2026-11-19-final` | `data/SNAPSHOT.md` |
| Final archive | sha256 `d67dfbf069007806342230ca36c81a5bfbe28340e577387da6c54e13f0fe4106`, 10,157,990 bytes; the provisional archive (sha256 `7fcedcd31523ec79604c80a347eb98a4156d7138e68890045b6e321495e16027`) stays in the release | `docs/DECISIONS.md` 2026-11-23; release assets |
| Nightly job | Scheduled 03:41 UTC in the data repo; checks out the frozen tag, installs with `uv sync --locked` and `npm ci`, downloads and hash-checks the newest `exports-*` asset, requires `status.json` `ok: true`, builds, trims files the app never fetches (789 to 570 files in `web/dist`), deploys a draft with `--no-build`, runs the 8-check `smoke_test.py`, then deploys to production only if it passes | `ops/undead-311-data/README.md`; `docs/KIRO_LOG.md` 2026-11-18 |
| Share images | 789 files in `web/dist`, was about 38,900 before drawing images only for the home page, the 3 tour zombies, neighborhoods and districts | `docs/KIRO_LOG.md` 2026-11-18 |
| Failure handling | A failed night keeps the last good deploy, writes an entry to the `nightly-state` release (`failure-history.json`), opens a `needs-human` issue in the ops repo, and the next good deploy shows the failure under `status.json` `history` | `ops/undead-311-data/README.md` |
| Nightly runs to date | 14 runs from 2026-11-18 to 2026-11-23: 9 success, 5 failure (runs 1 to 4 and 7). Fixes after the failures: `uv run --locked` (PR #32), draft deploy with smoke test (PR #33) | `gh api repos/ShroudedArrow/undead-311-data/actions/runs`; PRs |
| Deep property job | `deep-pbt` in the judged repo, nightly 05:17 UTC, 10x examples | `.github/workflows/deep-pbt.yml` |
| Content Security Policy and headers | One `_headers` file written by the web build; same-origin only; axe 0 third-party requests | `netlify.toml`; build-4 `report.md` |
| Netlify production-build guard | Netlify skips production builds so `main` cannot overwrite the nightly deploy | PR #29 |

## 11. Credits

Not recorded as usage. What is recorded:

- Entitlement: 4,000 hackathon credits per person plus 1,000 per month student credits (`docs/KIRO_SETUP.md` section 1).
- Owner-reported balance: 5,000 on 2026-11-12 and "about 5,000" on 2026-11-13 (`docs/DECISIONS.md` rows 2026-11-12 and 2026-11-13; `docs/READINESS.md`).
- No later balance, no per-run or per-session spend appears in the repo, the run logs or the channel. `docs/EXPERIMENTS.md` row 4 ("findings caught, iterations, credits") is empty, and `docs/AUDIT.md` H9 (a credits ledger) is "To do".
- Design choice that affects spend: the kiro-log hook is a command, not an agent prompt, because a workflow fires Stop once per step (`docs/AUDIT.md` Q4); per-save agent hooks were disabled.

## 12. Honest limits

My selection from the record, each with its source.

1. The test-town answer key was not hand-written by the owner. `docs/READINESS.md`: derived independently by Claude outside Kiro, cross-checked by a second derivation, one scenario (S05) spot-checked by the owner. `testing.md` says the owner should work it out by hand.
2. The excess is not shown. The headline placebo interval excludes 0 (-3,384; -3,570 to -3,200), so the baseline is uncalibrated. The adjusted stayed-fixed rate was removed and the confidence score is for ranking only.
3. Validation is records-based, not field-based. One reader, no second rater, no kappa. The 50 sites are recent and from four neighborhoods. Result: 20.0% repaired again (11.2% to 33.0%), up to 42.0% if ambiguous repairs count. The type split is lopsided (streetlight 9 of 18, pothole 1 of 23).
4. The Coroner's accuracy figure compares the pipeline with the Coroner agent's own labels on 200 rows. No human hand-label set exists. The 20-row owner check had suggested verdicts from Claude outside Kiro. New-system coverage was 89.9% in full-3 (legacy 99.8%).
5. Most zombies are not in the headline. 32,855 city re-reports (63% of headline plus city, 13,298 of them within an hour of closure) sit in their own tier. New-system re-reports cannot be told apart by origin, so 98 are tagged `source_unknown`.
6. The Skeptic reviewed 67 of 52,246 zombies. The committed `skeptic_objections.json` comes from the 200-case sample run, not the full data. Of the three final tour zombies, none has an objection (`docs/KIRO_LOG.md` 2026-11-22).
7. Name scrubbing is pattern-based. 80 closed cases still show a staff surname that is also a street name, measured against a 37-name check list that is not exhaustive. 23,672 case records hide their note.
8. Three high-frequency intersection points (224, 224, 207 cases) stay in the data, and their effect on counts has not been measured.
9. Counts are a floor: a zombie appears only if someone reports again. Rates are not ranked across neighborhoods without that context.
10. The 365-day survival horizon is not in `zombie-definition.md`; it is a statistics parameter the owner records (`docs/METHODS.md`).
11. Real-device performance is not verified. Frame times were profiled with software rendering and no GPU (`docs/PERF.md`; `docs/KIRO_LOG.md` 2026-11-19). The Spanish text is hidden until a native speaker reviews it (`docs/DECISIONS.md` 2026-11-17).
12. Kiro got things wrong along the way, as logged: kickoff UTC mislabel (section 7); the first guard probe was not blocked; a mirror check that could not fail (found by a mutant); task 27 ticked with no baseline wired (unticked, strict xfail added); a loosened schema to keep a test green (reverted); an earlier claim that no judging card had objections (it read one card per shard). Sources: `docs/KIRO_LOG.md` 2026-11-13, 2026-11-14, 2026-11-22.
13. Process gaps: two of four build runs ended on a loop maximum with no approval (build-2, build-3), plus build-1's last loop; no hosted preview was produced at build-4 (Netlify linking is a human step); 16 findings and 35 channel issues are open; ops#231 is a stale CI alert; `ruff check .` reports 36 errors outside the gated paths; `docs/EXPERIMENTS.md` has no results; the `cartographer` and `herald` agents have no recorded output.
14. This sheet's test counts were collected, not run. `make test` was not run for this change, and the archive's `run_report.json` was not available.

## 13. Three moments that show Kiro doing real work

My selection from the record. Other candidates: the Hypothesis finds in build-1 (duplicate IDs needing a total tie-break; a lone case open over 7 days cannot absorb its own duplicate), and the guard's secret-printing rule.

1. **The time-zone correction (2026-11-12).** The kickoff run treated new-system timestamps as UTC, which shifted its sample by 4 or 5 hours. Kiro tested the claim against data: 1,373 legacy cases closed with "Resubmitted as / See new case BCS-N" had new-system twins whose open time minus the legacy close time had a median of -2.6 minutes in every month, in daylight and standard time. It rewrote `times.py` (naive wall-clock digits, America/New_York, UTC and local stored, ambiguous and gap hours flagged), added a DST ordering property test, and corrected the data dictionary. Sources: `.kiro/steering/data-dictionary.md` "Time zones (corrected)", `docs/KIRO_LOG.md` 2026-11-12, `pipeline/tests/property/test_dst_ordering.py`.
2. **The baseline review loops and the placebo rule (2026-11-13 to 2026-11-17).** reviewer-stats on Opus found, over three runs and ten review passes on the durability-stats credibility loop (3, 5 and 2), that the baseline ran 40% high at sparse spots, 50% high with chains, and 9% high with a busy winter, and engine fixed each with seeded null-town tests. Then the full-data run showed the pre-registered placebo check failing (-3,322, interval excluding 0). The rule fixed in advance was followed: no tuning, excess withheld, adjusted rate removed. The full-data review notes the headline excess moved from -32,944 to -4,928 through two real defects (population and match area) before that stop. Sources: build-1, build-2 and build-3 run logs (ops#11, #117, #145), `reports/full-3/STATS_REVIEW.md`, `docs/DECISIONS.md` 2026-11-14, 2026-11-16, 2026-11-17.
3. **Reviewers catching what the implementers' own gates passed (build-4, 2026-11-15 to 2026-11-16).** All validate gates passed, yet reviewers found a raw `&amp;` in the first judge-tour card (UX-65, blocking), a `make capture` that never checked the frozen snapshot (ND1, major), raw copy keys on 1,991 city re-report cards (UX-53), and a map overlay canvas that took a Tab stop (UX-56). Each was fixed and re-reviewed; the engine's fixes for the capture check and GIF palette came on pass 2. Sources: `.kiro/workflow-runs/build-4/report.md` and `writeup-candidate.md`, `docs/KIRO_LOG.md` 2026-11-15 and 2026-11-16, ops#214.

## 14. Sources not in git

- Agent channel issues and comments: `ShroudedArrow/undead-311-ops` (private).
- Release `exports-snap-1120` and the `nightly-state` release, nightly run history: `ShroudedArrow/undead-311-data` (private).
- Final export archive contents (section 1) extracted 2026-11-23 from `exports-snap-1120.tar.gz` (hash above). The extracted copy is under `.local-data/`, which is gitignored.
