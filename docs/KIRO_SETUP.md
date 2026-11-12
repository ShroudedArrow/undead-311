# The Undead 311 — Kiro Setup and One-Shot Playbook

*How to set up Kiro so it can build The Undead 311 in one autonomous run, and which repos, MCP servers, and Powers are worth using. Updated Oct 31, 2026. Pairs with the starter kit (`undead-311-starter.zip`).*

---

## 0. What “one-shot” can realistically mean

**What Kiro can build in one autonomous run:**
- the data pipeline,
- the zombie detector and statistics,
- the web app,
- the MCP server,
- CI and the nightly refresh.

It needs well-defined specs, rich steering, real data on disk, and tests that act as gates.

**What it can’t do:**
- the in-person validation,
- judgment calls on the zombie definition,
- user interviews,
- the video,
- final design taste.

Those are about 20% of the work and most of what wins.

**The strategy**
1. **Front-load context on day 1:** steering, data, agents, hooks.
2. **Spend one careful hour reviewing the specs.**
3. **Launch one workflow** that implements, tests, and reviews everything in loops.
4. **Spend the remaining weeks** on validation, polish, and the video.

The one-shot itself is also a strong story for the Kiro write-up: “we wrote the specs; a workflow of agents built and reviewed it.”

---

## 1. Before you start (everyone on the team)

1. **Hackathon credits.** Each teammate fills out the Credit Request Form on the Devpost Resources tab now.
   - 4,000 credits per person.
   - Request by **Dec 1 at noon PT**; allow 48 business hours.
   - Redeem by Dec 4. Redeemed credits expire Dec 31.
2. **Student credits.** Verify at **kiro.dev/students** with your university email for 1,000 credits/month.
3. **Prerequisites:**
   - git and a GitHub account,
   - Python 3.11 and **uv**,
   - Node.js 20+ (for `npx`-based MCP servers and the web app),
   - Docker (optional; useful for running Kiro Crew 24/7).

---

## 2. Install and configure Kiro

1. **Kiro IDE:** download from kiro.dev and sign in. Specs, property-based testing, and Powers are strongest here.
2. **Kiro CLI:** `curl -fsSL https://cli.kiro.dev/install | bash`, then sign in. CLI 3.0 is the default experience as of October 2026.
3. **Kiro Web:** go to app.kiro.dev and connect GitHub. It’s good for cloud sessions that keep running while your laptop is closed.
4. **Models:** Claude Opus 5.5 and Sonnet 5.5 are available in Kiro.
   - **Opus, high reasoning effort:** requirements, design, and reviews.
   - **Sonnet:** routine implementation (cheaper).
5. **Turn on workflows.** They’re opt-in in every client:
   - **IDE / CLI:** enable them in the workspace configuration.
   - **Web:** Settings → Workflows → Enable workflows.
6. **Permissions for unattended runs.** Kiro 1.0 uses capability-based permissions. Ask Kiro to configure them:
   - **Allow without asking:** `make`, `uv`, `pytest`, `npm`, `npx`, and `git add`/`commit` inside worktrees.
   - **Always block:** destructive commands and force-pushes.
   - The starter kit’s guard hook adds a second layer.

---

## 3. Repositories (three, all public, all under the same GitHub account)

| Repo | Purpose | Notes |
|---|---|---|
| **`undead-311`** | Main project: pipeline, web app, MCP server, `/.kiro`, docs | OSI license (MIT or Apache-2.0) visible in About; `/.kiro` at root, never gitignored |
| **`undead-311-crew`** | The Kiro Crew App (bonus prize) | Must be a separate public repo, per the rules |
| **`boston-311-power`** | The installable Kiro Power wrapping our MCP server | A Power installed from GitHub needs `POWER.md` at the repo root, hence its own repo |

**External repos worth knowing**
- **`kirodotdev/KiroCrew`:** Crew’s source and docs. Install via the desktop app or the one-line installer instead of building it.
- **`ondata/ckan-mcp-server`:** the CKAN server we use for data discovery.
- **Templates:** `npm create vite@latest` (React + TS) is a standard development resource and allowed.

Disclose pre-existing code in the README. The starter kit’s README already does this, including that planning docs were drafted with an AI assistant.

---

## 4. The starter kit (drop into `undead-311`)

```
.kiro/steering/   product, tech, structure, zombie-definition, data-dictionary,
                  methods, language, testing, kiro-log, submission,
                  design-system, voice (12 files)
.kiro/settings/   mcp.json (4 MCP servers)
prompts/          00-kickoff … 07-design-pass (paste-ready prompts for Kiro)
docs/             PROJECT.md (the full write-up), KIRO_LOG.md, CRITERIA_MAP.md, HUMAN_NOTES.md
drafts/           human-written drafts (blog, social post, video script, Devpost text)
data/             README, sample/, labels/, SNAPSHOT.md (raw and processed data live outside the repo in $DATA_DIR)
docs/PREFLIGHT.md the bulletproofing checklist: finish section A before the build
.kiroignore       keeps secrets and large files out of agent context (IDE)
.gitignore, README.md
```

**Why it’s built this way**
- **Kiro generates the configs; we supply the domain knowledge.** Steering carries the knowledge Kiro can’t know: the zombie rules, the statistics, the data quirks, the language rules. Agents, hooks, and workflows are created *by Kiro* from the prompts. That way they match Kiro’s current file formats exactly, and they count as genuine Kiro use.
- **The rules are always loaded.** `zombie-definition.md` is set to always-included, so every agent applies identical rules.
- **Steering format rule:** the front matter must be the very first content in the file, with no blank lines before it.

**After copying the kit:**
1. Edit the DuckDB `--db-path` in `.kiro/settings/mcp.json` to an absolute path.
2. Commit.

---

## 5. MCP servers: what to use

| Server | Use it for | Verdict |
|---|---|---|
| **Context7** (`@upstash/context7-mcp`) | Current docs for DuckDB, MapLibre, deck.gl, Hypothesis, lifelines, Vite, so agents don’t invent APIs | **Use** |
| **DuckDB** (`mcp-server-motherduck`, local file, `--read-only`) | Agents query the *real* 311 data: column names, value distributions, edge cases. This is the biggest single boost to one-shot correctness | **Use** (it fails until the database file exists; reconnect after the kickoff step) |
| **CKAN** (`@aborruso/ckan-mcp-server`) | Discover Analyze Boston datasets, resource URLs, metadata, update times. Works with any CKAN portal | **Use** for setup and data discovery |
| **Playwright** (`@playwright/mcp`) | Agents open the built site, click through judge mode, check accessibility basics, and capture screenshots for review and the Devpost gallery | **Use** |
| **Undead 311 MCP** (we build it) | Exposes zombie queries to agents and Crew; becomes our Power | **Build** (spec 4) |
| **GitHub (agent channel)** (hosted GitHub MCP server, token scoped to one private repo) | Agents post status, findings, handoffs, and questions as issues in the private `undead-311-ops` repo; humans approve with labels. Setup in `prompts/08-agent-channel.md` | **Use** |
| AWS docs / AWS MCP servers | Only if you host on AWS | Optional |

**Two tips**
- **Custom agents and the workspace MCP list:** custom agents can include the workspace `mcp.json` servers via the `includeMcpJson` field. Ask Kiro to set it on agents that need data access.
- **If the CKAN package won’t start:** the project also publishes a hosted endpoint. Ask Kiro to configure it as a remote server instead.

---

## 6. Powers

- **Hosting power:** Kiro’s curated launch partners include **Netlify**. If you host there, installing its Power lets agents deploy previews directly, and it’s another Kiro feature for the write-up. Check kiro.dev/powers for anything else that fits; there are 60+ partner and community Powers.
- **Our own Power** (prompt 06): `POWER.md` plus `mcp.json` plus `steering/` in `boston-311-power`. Install it via **Powers panel → Add power from Local Path** to test, then from the GitHub URL.
- **Note:** auto-approval settings for a Power’s MCP tools aren’t copied at install; add them manually if wanted.

---

## 7. The build sequence (days 1–2)

| Step | What | Who / where | Time |
|---|---|---|---|
| **A. Kickoff** | Paste `prompts/00-kickoff.md`. Kiro discovers the dataset, downloads 2015+ CSVs, loads DuckDB, verifies the data dictionary, builds `data/sample/` and the Makefile | Data lead · CLI | 1–2 h (mostly downloads) |
| **B. Agents** | `prompts/01-agents.md`: Coroner, Skeptic, Cartographer, Herald, Data Steward, two reviewers. Use `/agent create` in the CLI or ask in the IDE; save to `.kiro/agents/` | Kiro lead · CLI | 30 min |
| **C. Hooks** | `prompts/02-hooks.md`: Kiro log (command, not agent), test-on-save, data validation, detector revalidation, Coroner eval, copy-lint, guard. Disable per-save hooks during big workflow runs | Kiro lead · IDE | 20 min |
| **C2. Agent channel** | `prompts/08-agent-channel.md`: private `undead-311-ops` repo, labels, a token limited to that repo, smoke test | Kiro lead · terminal + IDE | 20 min |
| **D. Specs** | `prompts/03-specs.md`: five specs. **Human gate:** read every requirement and the design’s correctness properties | Whole team · IDE | 2–3 h (worth it) |
| **E. One-shot run** | `prompts/04-workflow.md`: Kiro generates `build-undead-311.workflow.yaml`, then run it in the background | Kiro lead · IDE or CLI | Hours; overnight is fine |
| **F. Verify** | Read the workflow report, run `make test`, open the site; the UX reviewer’s screenshots land in `docs/screenshots/` | Everyone | 1–2 h |
| **G. Deploy** | Spec 5: CI and nightly refresh via GitHub Actions; host the static site | Data lead | 1–2 h |
| **H. Crew App** | `prompts/05-crew-app.md` in the `undead-311-crew` repo | Kiro lead | Half day, week 2–3 |
| **I. Power** | `prompts/06-power.md` in `boston-311-power` | Kiro lead | 1–2 h, week 3 |
| **J. Human design and copy pass** | `prompts/07-design-pass.md`: generic check, swap test, copy written by people, outside eyes. Do it after the build and again before the freeze | Design and story lead | Half day, twice |

**How the workflow does the work**
- **Recipes:** stored in `.kiro/workflows/*.workflow.yaml`. Each step runs in its own fresh agent session.
- **Loops and parallel branches:** `repeat` loops stop on a file check (for example, a review file saying `APPROVED`); `parallel` branches run concurrently.
- **Isolation:** each run gets its own git worktree.
- **Generation:** the easiest way to create a recipe is to ask Kiro, which is why prompt 04 describes the stages instead of hand-writing the file.
- **Our recipe:**
  1. **Worktree setup**, then engine and web scaffolding in parallel.
  2. **Per-spec loops:** implement → test gate → reviewer on a different model → repeat until approved (max 3).
  3. **Integration:** pipeline, build, end-to-end tests, and screenshots.
  4. **Report.**

**Fallback:** if a workflow misbehaves, open each spec’s `tasks.md` in the IDE and use **Run all tasks**, one spec at a time.

**Spec details that matter for one-shot**
- Requirements in EARS form (“WHEN … THE system SHALL …”).
- Ask Kiro to check them for contradictions and gaps before designing.
- The design must list **correctness properties** linked to requirements, so Kiro generates property tests: Hypothesis in Python, fast-check in TypeScript.
- When a property test fails, Kiro surfaces the exact failing case. Keep those moments for the write-up.

---

## 8. Credits: spend them wisely

- **Workflows cost more.** They coordinate several agents and repeat reviews, so they use more tokens than a single session.
- **Parallelize across accounts.** Credits are per person, so have each teammate run one spec’s workflow from their own account instead of burning one person’s credits.
- **Match model to task.** Strongest model only for requirements, design, and reviews; the faster model for implementation.
- **Fix, don’t restart.** Never rerun a whole workflow to fix one branch; fix the failing spec and rerun just that loop.
- **Crew’s usage** also draws on Kiro credits. Keep its daily and weekly jobs small.
- **Keep always-on steering lean.** Every always-included steering file rides along on every request. The full project write-up is about 9,000 tokens, so it’s now manual-only (`#project`); the always-on set is about 4,000 tokens.
- **Hooks can spend credits.** Agent-prompt hooks run a model each time they fire, and a workflow fires Stop once per step. The Kiro log hook is a plain command, and per-save hooks are switched off during big workflow runs.

---

## 8b. Before you launch: run the pre-flight checklist

Work through section A of `docs/PREFLIGHT.md`:
- eligibility (including the AWS/Amazon affiliation rule),
- credits received,
- a smoke-test workflow,
- branch protection and secret scanning,
- data stored outside the repo,
- a locked scope,
- a pre-registered zombie definition.

It takes about two hours and prevents most of the ways this project could fail.

## 9. What stays human (and wins)

1. **The zombie definition:** sanity-check results on real streets you know.
2. **In-person validation** of about 50 possible zombies. Publish the precision.
3. **Design taste:** autopsy cards, the time-lapse, the two-number scorecard.
4. **3–5 user conversations,** for one honest quote.
5. **The video:** script by Nov 20, footage by Nov 26, final cut by Dec 2.
6. **The Kiro write-up:** assembled from `docs/KIRO_LOG.md`.

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| A hook never fires | Kiro 1.0 replaced the old `*.kiro.hook` format; old-format files don’t run until migrated. Ask Kiro to migrate them, or run `kiro-cli agent migrate` |
| A steering file isn’t loading | Front matter must be the first lines of the file. `fileMatch` is reliable for workspace steering; use `auto` (with name and description) where needed |
| A custom agent is missing in Kiro Web | Agents committed under the repo’s `.kiro/` apply in cloud sessions automatically; personal agents in `~/.kiro/` don’t, unless you upload them through Kiro Web’s Cloud Config |
| The DuckDB MCP server fails at start | The database file doesn’t exist yet; run the kickoff step, then reconnect |
| A workflow aborts after 3 iterations | Read the run report, fix the spec or the failing test, rerun only that branch |
| Results look wrong on real data | Have the Skeptic agent review a sample; adjust `zombie-definition.md` (the only place parameters live) and log the change |
| A workflow can’t save its run files or tick off tasks | The guard hook must allow `.kiro/workflow-runs/**` and `tasks.md` checkbox updates |
| Parallel branches collide on shared files | Scaffold shared files (Makefile, package.json, schemas, copy files) in the setup step, and give each branch a file-ownership list |
| The DuckDB MCP server errors mid-run | The pipeline was rewriting the database; it should build to a temp file and rename it |
| Credits draining fast | Check for always-on steering that includes large files, agent-prompt hooks firing per step, or a workflow looping to its max iterations |

---

## 11. First-week schedule

| Day | Goal |
|---|---|
| **Sat Oct 31 (today)** | Credits requested by all three. Repos created, starter kit committed, Kiro installed. Kickoff (step A) started |
| **Sun Nov 1** | Agents, hooks, specs 1–3 written and reviewed. Launch the one-shot workflow overnight |
| **Mon Nov 2** | Review the workflow report; fix failures; first look at real zombies. Team confirms the plan |
| **Tue Nov 3 – Thu Nov 5** | Spec 5 (deploy); first live URL; draw the validation sample; lock the category |
| **Week 2+** | Follow the timeline in the project write-up (Crew App, Power, should-haves, validation, video) |

---

## Sources

- Kiroween 2026 official rules (credits, repos, Crew App bonus): https://kiroween.devpost.com/rules
- Kiro CLI install: https://kiro.dev/?df=ai_if
- Models and timeline: https://www.everydev.ai/developers/kiro
- Workflows: https://kiro.dev/docs/workflows/ · https://kiro.dev/docs/workflows/authoring/ · https://kiro.dev/docs/workflows/patterns/ · https://kiro.dev/changelog/web/introducing-workflows/
- Custom agents: https://kiro.dev/docs/custom-agents/creating/ · https://kiro.dev/docs/ide/whats-new-v1/agent-config/
- Hooks (current format and migration): https://kiro.dev/docs/cli/v3/hooks-migration/ · https://github.com/Enovatr-Labs/SpecRoute/wiki/Hooks
- Steering: https://kiro.dev/docs/steering/index
- Specs and property-based testing: https://kiro.dev/docs/specs/correctness/
- Powers: https://alpha.us-east-2.kiro.adc.aws.dev/docs/powers/installation/ · https://www.promptz.dev/powers/promptz-power-azure-monitoring
- Kiro Crew: https://kiro.dev/docs/crew/ · https://kiro.dev/docs/crew/apps/ · https://kiro.dev/docs/crew/running-24-7/ · https://github.com/ptias/KiroCrew
- MCP servers: CKAN: https://awesome.ecosyste.ms/projects/github.com%2Fondata%2Fckan-mcp-server · DuckDB: https://pypi.org/project/mcp-server-motherduck/0.6.1/ · Context7 and Playwright configs: https://github.com/berrydev-ai/install-mcp-servers
