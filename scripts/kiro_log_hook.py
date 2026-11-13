"""kiro-log hook (Stop). Standard library only; a command hook, so it spends no credits.

Appends ONE line to docs/KIRO_LOG.md in the kiro-log.md format:
`YYYY-MM-DD | <surface> | hook (kiro-log, auto) | <N> files changed: <short list> | -`
The surface comes from $KIRO_SURFACE (default "Web"). If nothing changed, or the summary equals the last auto
line (a workflow fires Stop once per step), nothing is written. The narrative line is added by a person or by
the workflow's report step. Always exits 0.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooklib

MAX_LIST = 5
TAG = "hook (kiro-log, auto)"


def changed_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root, capture_output=True, text=True, timeout=20, check=False,
    ).stdout
    files = [ln[3:].strip() for ln in out.splitlines() if ln.strip()]
    return sorted(f for f in files if not f.startswith("docs/KIRO_LOG.md"))


def summarize(files: list[str]) -> str:
    shown = ", ".join(files[:MAX_LIST])
    more = f" (+{len(files) - MAX_LIST} more)" if len(files) > MAX_LIST else ""
    return f"{len(files)} files changed: {shown}{more}"


def main() -> int:
    try:
        hooklib.read_payload()
        root = hooklib.repo_root()
        log = root / "docs" / "KIRO_LOG.md"
        files = changed_files(root)
        if not files or not log.exists():
            return 0
        summary = summarize(files)
        auto_lines = [ln for ln in log.read_text().splitlines() if TAG in ln]
        if auto_lines and summary in auto_lines[-1]:
            return 0
        surface = os.environ.get("KIRO_SURFACE", "Web")
        line = f"{dt.date.today().isoformat()} | {surface} | {TAG} | {summary} | -"
        text = log.read_text()
        with log.open("a") as f:
            f.write(("" if text.endswith("\n") else "\n") + line + "\n")
    except Exception as e:  # noqa: BLE001
        hooklib.log_stderr(f"kiro-log: skipped ({type(e).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
