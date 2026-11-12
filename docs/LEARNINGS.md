# Shared learnings (agents and humans read this before starting work)

One line each: `YYYY-MM-DD | who | learning`. Data quirks, library traps, failed approaches, things that worked.

2026-11-12 | kiro | In a git worktree, `git rev-parse --show-toplevel` returns the WORKTREE path, so the DATA_DIR fallback lands in `<worktree>/.local-data/data` when DATA_DIR is unset. Kiro Web sets DATA_DIR; elsewhere export it before a run.
2026-11-12 | kiro | The channel's list endpoint lagged about 10 s after a stop issue was closed (the kill switch still saw it on the first re-check). Expect the same lag when opening one.
2026-11-12 | kiro | Repo hooks in `undead-311/.kiro/hooks` were not loaded in a Kiro Web session whose workspace root was `/projects/sandbox`. Check hooks are live (a harmless forbidden command such as `git push --force --dry-run`) before trusting them.
