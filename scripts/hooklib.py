"""Shared helpers for the Kiro hook scripts (standard library only, no gh).

Hook scripts receive a JSON payload on stdin. The exact field names differ between Kiro surfaces,
so every accessor here tries several spellings and degrades gracefully.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CHANNEL_REPO = "ShroudedArrow/undead-311-ops"
API = "https://api.github.com"
TIMEOUT_S = 8


def repo_root() -> Path:
    """Repository root resolved at run time (never a hard-coded mount path)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, timeout=10
        )
        return Path(out.stdout.strip()).resolve()
    except Exception:  # noqa: BLE001
        return Path.cwd().resolve()


def read_payload() -> dict[str, Any]:
    """Parse the hook's stdin JSON; {} when there is none or it is not JSON."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {"_value": data}
    except Exception:  # noqa: BLE001
        return {}


def first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def tool_name(payload: dict[str, Any]) -> str:
    return str(first(payload, "tool_name", "toolName", "tool", "name") or "")


def tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    ti = first(payload, "tool_input", "toolInput", "input", "arguments", "args", "parameters")
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except Exception:  # noqa: BLE001
            ti = {"command": ti}
    return ti if isinstance(ti, dict) else {}


def token() -> str | None:
    return os.environ.get("GITHUB_CHANNEL_TOKEN") or None


def gh_request(method: str, path: str, body: dict | None = None) -> Any:
    """Call the GitHub REST API with the channel token. Raises on any failure (callers decide fail-open)."""
    tok = token()
    if not tok:
        raise RuntimeError("GITHUB_CHANNEL_TOKEN not set")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "undead-311-hooks",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def latest_run_dir(root: Path) -> Path | None:
    """The run directory to report to: $KIRO_RUN_ID if set, else the newest one that has channel.json."""
    runs = root / ".kiro" / "workflow-runs"
    rid = os.environ.get("KIRO_RUN_ID")
    if rid and (runs / rid).is_dir():
        return runs / rid
    cands = sorted(runs.glob("*/channel.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0].parent if cands else None


def log_stderr(msg: str) -> None:
    try:
        print(msg, file=sys.stderr)
    except Exception:  # noqa: BLE001, S110
        pass
