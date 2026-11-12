# 10 — Read-only audit by Kiro (run on the VM; repeat after the kickoff, after each build, and before the freeze)

Three stages, so the AI never holds write access during the audit:
1. **Collect (plain script, no AI):** GitHub settings, gathered with a read-only token.
2. **Review (Kiro, read-only tools only):** compares the plan, the repo, and the settings.
3. **Post (plain command, no AI):** the report goes to the agent channel.

## One-time: a read-only audit token
GitHub → Fine-grained token → access to all five repos → **Administration: Read**, **Contents: Read**, **Issues: Read**, Metadata: Read. Nothing with write. Add `export GITHUB_AUDIT_TOKEN="..."` to `~/.undead311.env` on the VM.

## Run it
```bash
cd ~/undead-311 && git pull
python3 scripts/preflight_check.py --json ~/logs/github-settings.json   # works anywhere (no gh/jq); collect_github_settings.sh is an optional extra on machines with gh and jq
timeout 1h kiro-cli chat --no-interactive --trust-tools=read,grep "$(cat prompts/10-audit.md | sed -n '/^## The audit prompt/,$p')" 2>&1 | tee ~/logs/audit-$(date +%F).md
GH_TOKEN="$GITHUB_CHANNEL_TOKEN" gh issue create -R YOUR_GITHUB_USERNAME/undead-311-ops --title "Audit $(date +%F)" --label type:finding --label to:human --body-file ~/logs/audit-$(date +%F).md
```
`--trust-tools=read,grep` lets Kiro read and search files without prompting, and nothing else. If your CLI version uses exact tool IDs instead, use `--trust-tools=read_file,grep_search`.

## The audit prompt
You are auditing The Undead 311 hackathon project. You may only read and search files. Do not modify anything.

Read: `docs/PROJECT.md`, `docs/PREFLIGHT.md`, `docs/AUDIT.md`, every file in `.kiro/` and `prompts/`, `README.md`, `.gitignore`, `.kiroignore`, `data/README.md`, and `~/logs/github-settings.json`.

Report, grouped by severity (BLOCKER, HIGH, MEDIUM, LOW), each with the file or setting as evidence and a one-line fix:
1. **Rules compliance** (from `.kiro/steering/submission.md`): license present; `.kiro/` not gitignored; required repos exist; anything that would fail the official rules.
2. **Security:** anything that looks like a secret or token in the repo (patterns such as `ghp_`, `github_pat_`, `ksk_`, `AKIA`, private keys); repo visibility (`undead-311-ops` must be private); branch protection on `main`; deploy keys and their access.
3. **Consistency:** contradictions between PROJECT.md, the steering files, and the prompts (data paths, hosting, Crew's role, the zombie definition, test properties). Placeholders left unfilled (`OWNER`, `/ABSOLUTE/PATH/TO`, `TODO-COPY`).
4. **Kit integrity:** steering front matter valid and first; `mcp.json` valid; every `make` target referenced by hooks or prompts listed in `structure.md`; agents and hooks present once they've been created.
5. **Pre-flight status:** for each item in `docs/PREFLIGHT.md` section A, say whether the repo shows evidence it's done, not done, or can't be checked from files.
6. **Plan risks:** anything in the plan that now looks wrong given the repo's current state (for example, the verified data dictionary contradicting an assumption).

End with the five most important fixes, in order. Be specific. Don't pad.
