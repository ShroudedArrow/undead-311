# 08 — Set up the GitHub agent channel (~20 minutes)

## 1. Create the channel repo (PRIVATE)
Private matters: issues in a public repo can be written by anyone, and agents read the channel, so a public channel is a prompt-injection risk.
```bash
gh repo create undead-311-ops --private --description "Agent channel for The Undead 311"
R="$(gh api user -q .login)/undead-311-ops"
for a in coroner skeptic cartographer herald data-steward reviewer-stats reviewer-ux engine web human; do gh label create "to:$a" -R "$R" --color 2E3134; done
for t in status handoff finding question proposal decision done; do gh label create "type:$t" -R "$R" --color CDCBC6; done
gh label create needs-human -R "$R" --color FF3EA5
gh label create blocked -R "$R" --color F26B1D
gh label create approved -R "$R" --color EFE08A
gh label create stop -R "$R" --color 000000   # opening an issue with this label halts any running workflow
```
Replace `OWNER` with your GitHub username in `.kiro/steering/agent-channel.md` and the prompts.

## 2. Create a narrowly scoped token
GitHub → Settings → Developer settings → **Fine-grained personal access token**:
- Repository access: **only** `undead-311-ops`
- Permissions: **Issues: Read and write** (Metadata: read is automatic). Nothing else.
- Expiration: mid-February 2027 (after winners are announced). Revoke it then.

## 3. Give it to Kiro without putting it in the repo
```bash
echo 'export GITHUB_CHANNEL_TOKEN="github_pat_..."' >> ~/.zshrc && source ~/.zshrc
```
- Launch Kiro from that terminal (apps started from the Dock don't see shell variables).
- Add `GITHUB_CHANNEL_TOKEN` to Kiro's **Mcp Approved Env Vars** setting (Kiro only expands approved variables).
- `.kiro/settings/mcp.json` already has the `github-channel` server pointing at GitHub's hosted MCP server. If the hosted server won't connect with your account, swap in the local Docker version: `ghcr.io/github/github-mcp-server` with `GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_CHANNEL_TOKEN}` and `GITHUB_TOOLSETS=issues,labels`.

## 4. Smoke test (paste into Kiro)
"Using the github-channel MCP server and agent-channel.md: open a run-log issue titled 'Run smoke-1: channel test' in OWNER/undead-311-ops, post one status comment in the required format, open a test finding issue labeled to:engine and type:finding, then list open issues labeled to:engine. Close both issues when done."

## 5. Optional: a mission-control board (5 minutes)
Create a GitHub Project (board view) linked to `undead-311-ops`. Turn on its built-in **auto-add** workflow for issues in that repo, and group columns by the `type:` label (or a Status field). Agents' findings, handoffs, and questions then appear on one board automatically. It also makes good B-roll for the video.

## 6. For the judges
Before the freeze, run `make channel-export` (ask Kiro to write the script) so `docs/AGENT_CHANNEL.md` in the public repo shows how the agents coordinated. Pick two or three good threads to link from the Kiro write-up.
