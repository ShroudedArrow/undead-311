# 00a — Windows setup, done by Kiro (paste into Kiro chat, IDE or CLI)

Before pasting: install the Kiro IDE (kiro.dev/downloads), sign in, extract this kit into a folder such as `C:\Users\<you>\code\undead-311`, and open that folder in Kiro.

---

You're setting up our hackathon project on Windows (native, no WSL). Use PowerShell. Ask before installing each tool, and STOP at every PAUSE so I can do that step myself.

1. **Tools.** Check for and install, with winget: Git (`Git.Git`), GitHub CLI (`GitHub.cli`), Node.js LTS (`OpenJS.NodeJS.LTS`), uv (`astral-sh.uv`), and GNU Make (search winget for a maintained make package). Then run `uv python install 3.11`. Install the Kiro CLI with `irm 'https://cli.kiro.dev/install.ps1' | iex`. Print the version of every tool.
2. **PAUSE:** tell me to run `gh auth login` (GitHub.com, HTTPS, browser) and `kiro-cli` to sign in, in the terminal.
3. **Windows adaptations** (part of the first commit):
   - Add `.gitattributes` with `* text=auto eol=lf`, so line endings don't break scripts or CI.
   - Any script called by a hook or Makefile target must be Python, run with `uv run python scripts/<name>.py`. No bash-only scripts.
   - If MCP servers in `.kiro/settings/mcp.json` that use `npx` or `uvx` fail to start, change them to `"command": "cmd"` with `"args": ["/c", "npx", ...]`.
4. **Data folder outside the repo.** Create `%USERPROFILE%\undead311-data\raw` and `\processed`. Set a persistent user environment variable with `setx DATA_DIR "%USERPROFILE%\undead311-data"`. Put the absolute path to `%USERPROFILE%\undead311-data\processed\undead311.duckdb` (JSON-escaped) in the duckdb server's `--db-path` in `.kiro/settings/mcp.json`.
5. **Username.** Replace every `OWNER` in `.kiro/` and `prompts/` with my GitHub username (`gh api user -q .login`). Confirm none remain.
6. **Plan freeze.** Append to `docs/DECISIONS.md`: `| <today> | Plan frozen; changes only through this log | Protect the build from churn | Keep editing the plan |`
7. **Repos.** Create the private GitHub repo `undead-311` with an MIT license, connect this folder to it, commit with message `chore: starter kit and pre-registered zombie definition`, and push. Then create private repos `undead-311-crew`, `boston-311-power`, and `undead-311-data` (MIT license).
8. Skip collaborators (solo project).
9. **Agent channel.** Create the private repo `undead-311-ops` and all labels listed in `prompts/08-agent-channel.md` (convert the bash loops to PowerShell).
10. **PAUSE:** tell me to create the fine-grained token myself (access to ONLY `undead-311-ops`; Issues: Read and write; expires mid-February) and to set it MYSELF in a separate terminal with `setx GITHUB_CHANNEL_TOKEN "<token>"`. I will not paste the token into this chat.
11. **Versions and permissions.** Write the Kiro IDE and CLI versions at the top of `docs/KIRO_LOG.md`. Propose a permissions configuration that lets `make`, `uv`, `npm`, `npx`, `pytest`, and `git add`/`git commit` run without asking, and always blocks `rm -rf`, `Remove-Item -Recurse` on the repo or `DATA_DIR`, and `git push --force`. Show it to me before saving.
12. **Finish** with a checklist: what's done, and what I still need to do by hand.
