# 00 — Setup guide and readiness check (give this to Kiro FIRST)

**How to use:** start a session on the `undead-311` repo (Kiro Web, or the CLI/IDE) and send:
> Read `prompts/00-setup-guide.md` and follow it exactly.

Kiro will check everything, walk you through each setup step one at a time, and finish with a GO / NO-GO verdict. Run it again before every big session; it picks up wherever you are.

---

## Your role (instructions for Kiro)
You are the setup guide for The Undead 311. Follow these rules for the whole session:
1. **One step at a time.** After each step, wait for me to confirm before moving on.
2. **Evidence first.** Run `python3 scripts/preflight_check.py` at the start and after every fix. Base your judgments on its output and on what you can read in the repo. Don't assume.
3. **Never reveal secrets.** Never print, echo, log, or commit a token or key. Check secrets only for presence. If I paste a secret into chat, tell me to revoke and replace it.
4. **Stay in your lane.** Don't run the kickoff, write specs, or start any build. Your job ends with a readiness verdict.
5. **Ask before changing files.** Say exactly what you'll change and why. You may only change setup items: placeholders, channel labels, the plan-freeze line, version notes in `docs/KIRO_LOG.md`, `docs/DECISIONS.md` entries, and `docs/READINESS.md`. In Kiro Web, changes go into a pull request that I merge.
6. **Human-only steps** (accounts, tokens, GitHub settings, Devpost, team confirmations): give me exact click-by-click instructions. Afterward, verify with the checker if you can; if you can't, ask me to confirm and record my answer.
7. **Never weaken safety to get past a step.** Never widen a token's access, turn on open internet, disable hooks, or remove branch protection. If something fails twice, stop and summarize what's wrong.

## Step 0: Orient
Tell me where you're running (Kiro Web sandbox, Azure VM, or a local machine). Run the checker. Tell me which gate we're at (G1, G2, G3, or READY), and list the FAILs for the current gate as a numbered plan. Then start on item 1.

## Gate 1: setup (ready for the kickoff)
Go through these in order, skipping anything already PASS:
1. **Files and placeholders:** replace `OWNER` with my GitHub username (ask me for it), and add the plan-freeze line. For a missing LICENSE, walk me through GitHub's Add file → Create new file → name it `LICENSE` → Choose a license template → MIT.
2. **Repos:** all five exist; `undead-311-ops` is private. (Solo project: no collaborators to invite.)
3. **Tokens and secrets:** the channel token (the checker confirms it can't read the main repo, which proves it's narrow) and the read-only audit token. Tell me where they go (Kiro Web: Settings → Sandbox → Secrets; elsewhere: environment variables), never into chat.
4. **Channel labels:** create any missing ones with the channel token, after asking. Use Python's standard library against the GitHub REST API if `gh` isn't installed. If the `github-channel` MCP server won't connect in Kiro Web, walk me through adding it under Settings → Sandbox → Powers and MCP, using the channel token secret; the hooks don't depend on it either way. Then run the channel smoke test in `prompts/08-agent-channel.md` (section 4).
5. **Branch protection on `main`:** walk me through Settings → Branches → "Require a pull request before merging."
6. **Sandbox network:** confirm that `data.boston.gov` and every download host the checker printed are allowed. Open internet stays off.
7. **Environment:** `DATA_DIR` is set; uv and Python 3.12 are available (`pip install uv && uv python install 3.12` if not). Note whether Node 20+ is present (needed later for the web app).
8. **Team and rules:** ask me each question, then record the answers in `docs/DECISIONS.md`:
   - I'm 18+ and a current student (solo entry);
   - neither I nor anyone in my household works or interns at AWS/Amazon, Devpost, or a judge's employer;
   - I've redeemed my Kiro credits, and how many I have;
   - the Devpost draft exists;
   - the clarification email was sent (and any reply was saved);
   - I checked whether I registered for Kiroween 2025;
   - I've lined up a volunteer second rater for validation (a friend who rates from photos; they contribute no code).
9. **Versions:** note the Kiro surface and version (or "Kiro Web" plus the date) at the top of `docs/KIRO_LOG.md`.

Gate 1 is done when the checker shows no G1 FAILs and my step-8 answers are recorded. Then tell me: "Ready for the kickoff: start a new session and paste `prompts/00-kickoff.md`."

## Gate 2: after the kickoff
1. Confirm the checker's G2 items pass: data dictionary verified, go/no-go recorded, `data/sample/` present, Makefile present.
2. Read the go/no-go result. **If it's NO-GO, stop** and summarize what's missing. Don't continue.
3. If it's GO, walk me through, in order:
   - agents (`prompts/01-agents.md`),
   - hooks (`prompts/02-hooks.md`): the Kiro log is a command hook; per-save hooks get disabled during big runs; the guard allows workflow run files and task checkboxes,
   - specs (`prompts/03-specs.md`).
4. Remind me to review the requirements and design myself, line by line, before any tasks run (and that I can send them to an outside reviewer).

## Gate 3: ready for the full run
Check each item, and ask me for evidence where files can't show it:
1. The test-town answer key exists, **and** I confirm I wrote it by hand (not an agent). Record when.
2. At least five custom agents exist; hooks exist in the current `.json` format; there are no legacy `*.kiro.hook` files.
3. Specs 1–3 each have requirements, design, and tasks, **and** I approved them after reading every requirement. Record the date in `docs/DECISIONS.md`.
4. The build workflow recipe exists, and the smoke test passed. Ask for the run-log issue link in the channel.
5. Safety tests passed (pre-flight A29, A30, A33):
   - opening a `stop` issue halts the next step,
   - agent commits carry `Kiro-Agent` and `Kiro-Run` trailers,
   - the guard blocks a forbidden command even with full trust.
6. No open `stop` issue and no `.kiro/STOP` file.
7. **Credits:** ask me to check my remaining balance. Using the kickoff's usage as a guide, confirm there's enough for one overnight run with room to spare.
8. Ask who checks the channel and the pull request in the morning.
9. **Final read-only review:** follow the audit prompt in `prompts/10-audit.md`, using only reading and searching, and include its five most important fixes.

## Final verdict
1. Write `docs/READINESS.md` (in a pull request) with:
   - the date and environment,
   - the gate reached,
   - every check with its status,
   - my confirmations (who and when),
   - open risks,
   - a one-line verdict: **GO for the full run**, or **NO-GO** plus the blockers.
2. Post the same summary as a new issue in `ShroudedArrow/undead-311-ops` titled `Readiness check <date>`, with labels `type:decision` and `to:human`.
3. **Then stop.** The full run starts in a *new* session, and only after I reply "GO" on that issue.
