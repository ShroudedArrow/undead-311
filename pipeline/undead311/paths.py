"""Data and repo paths with the tech.md self-correcting fallback (REQ-ING-PATH).

`DATA_DIR` is used only when it is an existing, writable directory (the same rule as the Makefile, ops#9).
Otherwise the fallback is `<repo root>/.local-data/data`, created on demand. In a git worktree the repo root is
the MAIN checkout's root (from `git rev-parse --git-common-dir`), so every worktree shares one data folder.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    """Root of the main checkout, resolved at run time (REQ-ING-PATH.2). Never a hard-coded mount path."""
    cwd = Path(start) if start is not None else Path.cwd()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd, capture_output=True, text=True, check=True,
        )  # fmt: skip
        common = Path(out.stdout.strip()).resolve()
        if common.name == ".git":
            return common.parent
        return common  # bare layout: the common dir itself
    except (OSError, subprocess.CalledProcessError):
        return Path(__file__).resolve().parents[2]


def _usable(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def data_dir(start: Path | None = None) -> Path:
    """DATA_DIR if it is an existing writable directory, else `<repo root>/.local-data/data` (created). REQ-ING-PATH.1."""
    env = os.environ.get("DATA_DIR")
    if env and _usable(Path(env)):
        chosen = Path(env).resolve()
    else:
        chosen = repo_root(start) / ".local-data" / "data"
        chosen.mkdir(parents=True, exist_ok=True)
        if env:
            print(f"[paths] DATA_DIR={env!r} is missing or not writable; using {chosen}", file=sys.stderr)
    print(f"[paths] data dir: {chosen}", file=sys.stderr)
    return chosen
