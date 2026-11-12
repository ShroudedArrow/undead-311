# 04 — The one-shot workflow (ask Kiro to generate it, then save it)

Prerequisites: workflows enabled; specs 1–3 approved (requirements, design, tasks); `docs/PREFLIGHT.md` section A complete.

**Smoke test first (15 minutes, low credits):** ask Kiro to create and run a tiny recipe `smoke.workflow.yaml` with one implement step ("add a `make hello` target that prints the DATA_DIR"), one validate gate, and one reviewer. Confirm worktree creation, agents, permissions, MCP access, hooks, and the stop condition all work before the real run.

Paste into Kiro:

"Create a reusable workflow recipe at .kiro/workflows/build-undead-311.workflow.yaml that implements the approved specs in .kiro/specs/. Structure:
0. channel: open the run-log issue in `ShroudedArrow/undead-311-ops` via the github-channel MCP server (title `Run {{run_id}}: build-undead-311`, label `type:status`) and save its number to `channel.json` in the run directory. Every later step starts by reading open issues labeled `to:<its-role>` and ends with one status comment. Implementers close finding issues with commit links. Stop conditions stay file-based.
1. setup: create an isolated git worktree for this run, then scaffold ALL shared files first (pyproject.toml, package.json, Makefile, /schemas/, web/src/copy/en.json, the test-town fixture CASES) and commit them. `expected_zombies.json` is written by a person before the run and must already exist; agents never edit it, so parallel branches don't collide. Give each branch a file-ownership list (engine owns pipeline/, web owns web/) and forbid edits outside it.
2. parallel: implement zombie-engine and haunted-web scaffolding at the same time (web uses fixture data from data/sample until the engine exports real files).
3. For each spec, a repeat loop (max 3 iterations, abort if unmet): implement the next tasks → run `make test` and `ruff` as a validate gate that writes PASS/FAIL to a JSON file → reviewer-stats (for engine/stats) or reviewer-ux (for web) on a different model than the implementer → stop when the review JSON verdict is APPROVED and the gate is PASS.
4. Then durability-stats the same way.
5. integrate: run `make pipeline` on data/sample, `make build`, `make e2e`; reviewer-ux takes screenshots of every page into docs/screenshots/.
5b. design gate: reviewer-ux must pass design-system.md's banned-defaults list and `make copy-lint` must report no banned words (TODO-COPY markers are allowed until the human copy pass).
5c. preview: deploy a preview of the worktree's build (Netlify deploy preview or equivalent) and have reviewer-ux run its Playwright review against that URL; post the preview link to the run-log issue so teammates can click it.
5d. retro: a final step reads the run-log issue and the run artifacts, adds up to three lines to docs/LEARNINGS.md, and drafts one candidate line for the Kiro write-up.
All agent commits carry the `Kiro-Agent` and `Kiro-Run` trailers (structure.md).
6. report: summarize what was built, failing items, and next steps into the run directory, and append to docs/KIRO_LOG.md.
Use the strongest model with high effort for review steps and a faster model for implementation steps."

Solo project: run the main repo through THIS one workflow (its parallel branches and worktrees replace separate per-person sessions). Use separate sessions only for the separate Crew and Power repos and for read-only audits. Run it from Kiro Web, the CLI, or the IDE in the background. Watch progress in the Workflows panel; answer any step that pauses for input. Merge the worktree when the report is clean.

If workflows feel unstable, fall back to the IDE: open each spec's tasks.md and use "Run all tasks", one spec at a time, in the order above.
