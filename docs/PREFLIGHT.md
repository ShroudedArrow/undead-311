# Pre-flight checklist: bulletproof before the one-shot run

Work through section A before launching the build workflow. B and C can follow during the week. D is for submission day. Owner initials go in the last column.

## A. Before launching the build (blocking)

### Eligibility and team (rules risks that can disqualify you)
| # | Check | Done |
|---|---|---|
| A1 | You are at least the age of majority where you live (solo entry) | |
| A2 | **No member, or anyone in their immediate family or household, works for AWS/Amazon (including internships), Devpost, or a judge’s employer.** Amazon affiliates count | |
| A3 | You are a current student, with LinkedIn profile, student email, year/degree, and school ready (Best Student Project) | |
| A4 | Check whether anyone registered for Kiroween 2025 (the $2K bonus) | |
| A5 | Solo entry: no team agreement needed. If anyone helps (for example, a friend as the second validation rater), they’re credited as a helper, not a team member, and contribute no code | |
| A6 | No code from personal projects is reused. Pre-existing code is limited to open-source frameworks/libraries, disclosed in the README | |

### Kiro and credits
| # | Check | Done |
|---|---|---|
| A7 | You have requested **and received** your 4,000 hackathon credits, plus student credits. Solo means one account’s credits, so budget runs accordingly | |
| A8 | Kiro IDE and CLI installed and signed in; workflows enabled for the workspace | |
| A9 | `.kiroignore` added to Settings → Agent Ignore Files (IDE). It isn’t enforced in Kiro Web; the rule lives in `tech.md` (data lives outside git tracking: $DATA_DIR outside the repo on local or Azure runs; the gitignored .local-data/ folder in Kiro Web) | |
| A10 | MCP servers connected (Context7, DuckDB at an absolute path in the data folder (see A18), CKAN, Playwright) | |
| A11 | Permissions: tests and builds allowed without prompts; destructive commands blocked; guard hook in place | |
| A12 | Smoke-test workflow ran end to end (`prompts/04-workflow.md`) | |
| A13 | Someone is reachable during the run, since workflows pause when a step needs input | |

### Repo and safety
| # | Check | Done |
|---|---|---|
| A14 | Three GitHub repos created (main, crew, power), plus `undead-311-data` for the nightly refresh | |
| A15 | License file added and detected (shown in the About section) | |
| A16 | Branch protection on `main`: merges via pull request, CI required. Workflow runs work in worktrees | |
| A17 | Secret scanning and push protection on; `.env` gitignored; no tokens anywhere in the repo | |
| A18 | Data downloaded and stored outside git tracking: $DATA_DIR outside the repo on local or Azure runs; the gitignored .local-data/ folder in Kiro Web; `data/SNAPSHOT.md` records hashes and date | |

### Method credibility (do before seeing results)
| # | Check | Done |
|---|---|---|
| A19 | **Scope locked:** public right-of-way infrastructure only. No case types about people; no private-residence complaints | |
| A20 | **Zombie definition pre-registered:** `zombie-definition.md` committed with today’s date before running on full data. Any later change goes in its change log with a reason | |
| A21 | Design direction confirmed by the team (`design-system.md`); voice rules agreed (`voice.md`) | |

### Build-run safety (added in the second audit pass)
| # | Check | Done |
|---|---|---|
| A22 | Always-on steering is lean: the full write-up loads only via `#project` (it’s about 9,000 tokens per request otherwise) | |
| A23 | Hooks are cost-safe: the Kiro log is a command hook, and per-save hooks are disabled during big workflow runs | |
| A24 | The guard hook allows `.kiro/workflow-runs/**` and `tasks.md` checkbox updates, but blocks edits to steering, settings, hooks, and agents | |
| A25 | The “test town” golden fixture and its expected output exist, so the build has a correctness anchor | |
| A26 | Shared files (Makefile, package.json, pyproject, schemas, copy files) are scaffolded before any parallel branches start | |
| A27 | Agent channel repo `undead-311-ops` is **private**; its token can only read and write issues in that one repo, is stored outside the repo, and is listed in Kiro’s approved MCP env vars | |
| A28 | Channel smoke test passed: a run-log issue, a status comment, and a routed finding all appeared and closed | |
| A29 | Kill switch tested: creating `.kiro/STOP` blocks the next step of the smoke-test workflow; deleting it lets the run continue | |
| A30 | Agent commits in the smoke test carry the `Kiro-Agent` and `Kiro-Run` trailers | |
| A31 | Kiro IDE and CLI versions recorded in `docs/KIRO_LOG.md`; automatic updates off if your install allows it. Kiro changed its hook and agent formats in 1.0, and a mid-build update could do it again | |
| A32 | Devpost project draft created now (solo) | |
| A33 | Unattended runner tested on the Azure VM (`prompts/09-azure-runner.md`): with `--trust-all-tools` on, the guard hook still blocks a forbidden command, and opening a `stop` issue halts the next step | |

## B. During the first week

| # | Check | Done |
|---|---|---|
| B1 | Validation sample drawn **randomly with a fixed seed** and committed before any field visit (no cherry-picking) | |
| B2 | Kill criteria agreed: if precision on the validation sample is below an agreed bar by Nov 12, narrow scope (e.g., potholes and sidewalks only) instead of polishing | |
| B3 | Scope-cut order agreed (stretch → should → must), so nobody argues under deadline pressure | |
| B4 | Host chosen and set up (Netlify via its Power, or GitHub Pages) | |
| B5 | Nightly refresh lives in `undead-311-data`. GitHub disables scheduled workflows in public repos after 60 days without activity, so calendar a weekly check during judging | |
| B6 | Raw snapshot mirrored (e.g., as release assets in the data repo), so results stay reproducible if the city’s files change | |
| B7 | Capture screenshots of Kiro as you go: specs, workflow panel, property-test failures, hooks firing. These views are temporary, and you’ll want them for the write-up and video | |
| B8 | `docs/HUMAN_NOTES.md` started; each teammate adds a line when something surprises them | |
| B9 | Optional: ask Northeastern’s Boston Area Research Initiative (BARI), which studies Boston 311 reporting, for a 15-minute methods sanity check. Check whether their neighborhood “custodianship” measures can be reused (and under what license) for the reporting-bias context | |
| B10 | Check the academic calendar: finals and Thanksgiving week can eat the last two weeks, so front-load the build | |
| B11 | Written clarification request sent to support@devpost.com (the rules ask for this when a term may be ambiguous): (1) the live site refreshes data nightly from a separate repo after the deadline, while the judged code stays frozen; (2) agents coordinate in a private supporting repo, exported to the public repo for judges. Save the reply | |
| B12 | Validation calendar set: **snapshot Fri Nov 20** → draw the seeded sample the same day → field visits Sat–Sun Nov 21–22 in daylight (sunset is around 4:15 PM) → second rater scores your photos by Tue Nov 24 | |
| B13 | “Done” defined for the first overnight run: test town passes exactly, the pipeline runs on the sample, and the map renders with zombies. Anything else is a fix-day task, not a rerun | |

## C. Before the freeze (Dec 2)

### Product quality
| # | Check | Done |
|---|---|---|
| C1 | Fresh-machine test: a teammate clones the repo on a clean Mac or Windows machine and runs the README quickstart on `data/sample/` | |
| C2 | Performance: initial load under about 3 MB of data; usable on a mid-range phone; tested on **iPhone Safari** and Chrome | |
| C3 | Accessibility: keyboard path through judge mode, reduced motion, contrast (pink and orange never used as text), table view works | |
| C4 | “Data as of <date>” visible; video, README, and validation numbers all match the judging snapshot | |
| C5 | Footer disclaimer (“Independent project. Not affiliated with the City of Boston.”); no city seal or logos; OpenStreetMap credit; data and font licenses listed | |
| C6 | No analytics cookies; no personal data collected anywhere (including stretch features) | |
| C7 | `make copy-lint` passes with zero TODO-COPY markers; human design pass done twice | |
| C7b | Judge mode shows only confirmed zombies (from the validation set) and runs on the frozen snapshot, so its numbers match the video | |
| C7c | Fonts and basemap tiles are self-hosted; the site makes no runtime requests to outside services | |

### Video and media
| # | Check | Done |
|---|---|---|
| C8 | Video under 3:00, public on YouTube (not unlisted), with no copyrighted music and no third-party logos (blur truck logos and chat-app branding) | |
| C9 | No identifiable residents or city workers filmed without consent; filmed safely and legally from public space | |

### Optional but recommended
| # | Check | Done |
|---|---|---|
| C10 | Send a short, polite heads-up to Boston’s 311/analytics team with the link and the methods page, inviting corrections. It’s fairer, and any reply strengthens the Impact case | |

## D. Submission day (target Thu Dec 3; deadline Fri Dec 4, 2:00 PM PT / 5:00 PM ET)

| # | Check | Done |
|---|---|---|
| D1 | Every link checked in a private/incognito window: app, GitHub repos, YouTube, blog, social post | |
| D2 | Repos public; `/.kiro` present and not gitignored; license detected | |
| D3 | Git tag `kiroween-submission` on the submitted commit; mentioned in the Devpost write-up. **No code pushes to the judged repo after the deadline** | |
| D4 | Devpost form complete: category, bonuses, student details for all three, Crew App repo link, blog and social URLs, data/code disclosures | |
| D5 | Uptime monitor on the live URL; spend caps confirmed; someone on watch through **Jan 29** | |
| D6 | Social post starts with `#KiroweenHackathon26`; blog mentions Kiroween 2026; both published before the deadline | |
| D7 | The social post comes from a profile that matches your Devpost identity; the rules allow disqualifying mismatched profiles | |
