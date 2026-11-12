# 11 — Running everything in Kiro Web (browser only; nothing on your laptop)

Kiro Web runs each task in an isolated cloud sandbox that clones your repo and can't reach your machine. It needs a Pro, Pro+, Pro Max, or Power subscription: log in at app.kiro.dev first and check you have access. If you don't, use the Azure runner (`prompts/09-azure-runner.md`) instead.

## 1. Connect only your repos (5 min)
Connect GitHub and grant access to **only** the five project repos. Kiro's docs warn the agent follows instructions found in repository code, so never add repos you don't control.

## 2. Sandbox settings (Settings → Sandbox, 10 min)
- **Internet access:** "Common dependencies" (package registries) plus a custom allow-list. Add only what the project needs:
  - `data.boston.gov` and the host its file downloads redirect to (check the first download's URL)
  - the Context7 MCP domain, if you keep that server
  - Do NOT choose Open internet.
- **Environment variable (not secret):** `DATA_DIR=/tmp/undead311-data`
- **Secret:** `GITHUB_CHANNEL_TOKEN` only (the token limited to `undead-311-ops` issues). Add `GITHUB_AUDIT_TOKEN` only in sessions that run the audit. Secrets can leak through code or logs, so give each task only what it needs.
- **Environment configuration / setup commands:** `pip install uv && uv python install 3.12`, plus `npm ci` once `web/` exists.

## 3. MCP differences in the cloud
- **Playwright and a headless Chrome are already built into every sandbox.** Our `playwright` entry isn't needed there.
- **The DuckDB MCP server's absolute path won't exist in the sandbox.** In cloud sessions, agents query DuckDB through Python in the shell instead (`uv run --with duckdb python ...`). Expect that server to fail to start there; that's fine.
- **Context7 and the GitHub channel** work if their domains are reachable.

## 4. Data in short-lived sandboxes
Each task gets a fresh sandbox, so downloaded data doesn't carry over.
- Tests and judge mode use the committed `data/sample/`, so most tasks need no download at all.
- For full-data tasks: once the nightly GitHub Actions job in `undead-311-data` exists, have it attach the processed Parquet snapshot to a GitHub Release. Sessions then download one file instead of rebuilding from the city's CSVs.
- Until then, the kickoff downloads the CSVs itself (allow a few minutes).

## 5. Test it (15 min) before relying on it
Start a session on `undead-311` and send:
"List the MCP servers you can use. Download the most recent Boston 311 CSV from data.boston.gov into $DATA_DIR/raw and report its row count. Post one status comment to a run-log issue titled 'Run web-smoke-1' in OWNER/undead-311-ops following agent-channel.md, then close it."
If all three work, you're set.

## 6. Then use Web for everything
- **Kickoff:** paste `prompts/00-kickoff.md` into a new session. Review the pull request it opens.
- **Specs:** Web supports feature, bugfix, and quick specs. Review requirements and design before tasks.
- **Overnight builds:** start the build workflow in a session and close the browser; the agent keeps working. Up to 10 sessions can run at once.
- **Audit:** run `prompts/10-audit.md` in a session using a read-only auditor agent (read and search permissions only), with `GITHUB_AUDIT_TOKEN` as that session's only extra secret.
- **Approvals:** Kiro Web never merges on its own; it opens pull requests, and branch protection on `main` keeps it that way.

## What still lives elsewhere
- **Nightly data refresh:** GitHub Actions in `undead-311-data` (not Kiro).
- **Kiro Crew App:** Crew isn't part of Kiro Web. Build and demo it in Docker or on a short-lived Azure VM (optional; off by default to save hours). Running it live during judging is optional.
