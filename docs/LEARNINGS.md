# Shared learnings (agents and humans read this before starting work)

One line each: `YYYY-MM-DD | who | learning`. Data quirks, library traps, failed approaches, things that worked.

2026-11-12 | kiro | In a git worktree, `git rev-parse --show-toplevel` returns the WORKTREE path, so the DATA_DIR fallback lands in `<worktree>/.local-data/data` when DATA_DIR is unset. Kiro Web sets DATA_DIR; elsewhere export it before a run.
2026-11-12 | kiro | The channel's list endpoint lagged about 10 s after a stop issue was closed (the kill switch still saw it on the first re-check). Expect the same lag when opening one.
2026-11-12 | kiro | Repo hooks in `undead-311/.kiro/hooks` were not loaded in a Kiro Web session whose workspace root was `/projects/sandbox`. Check hooks are live (a harmless forbidden command such as `git push --force --dry-run`) before trusting them.
2026-11-13 | kiro | The workflow engine matches a repeat's stopCondition path literally against step prompts: a prompt that names the stop file by a relative path doesn't count, and the loop gets a "may never stop" warning. Write stop files by the same absolute path.
2026-11-13 | kiro | A new stop issue isn't seen for up to ~40 s (list lag plus the kill switch's 30 s cache); in smoke-2 two steps ran after it was opened. Use `.kiro/STOP` for an instant halt.2026-11-13 | engine | In a fresh git worktree run `uv sync --group dev` and `cd web && npm ci` before `make test`: node_modules and .venv are not shared between worktrees. Also: running pipeline/scripts/build_test_town.py rewrites test_town.csv (identical output today).
