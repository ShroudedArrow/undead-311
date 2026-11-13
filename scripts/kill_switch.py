"""Kill switch hook (PreTaskExec, and PreToolUse for shell). Standard library only.

Blocks (exit 2) when:
  * `.kiro/STOP` exists in the working tree, or
  * ShroudedArrow/undead-311-ops has an OPEN issue labeled `stop`.
Fail-open: if GitHub can't be reached (or no token is set), the step is allowed, so an outage can't stall a run.
The GitHub answer is cached for CACHE_S seconds in the gitignored .local-data/ folder to stay well inside API limits.

Manual check: `python3 scripts/kill_switch.py --check` prints the decision and exits 0/2.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooklib

CACHE_S = 30
BLOCK = 2


def open_stop_issues(root: Path) -> list[int] | None:
    """Open `stop` issue numbers, or None if unknown (GitHub unreachable)."""
    cache = root / ".local-data" / "kill_switch_cache.json"
    try:
        c = json.loads(cache.read_text())
        if time.time() - c["at"] < CACHE_S:
            return c["issues"]
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        items = hooklib.gh_request("GET", f"/repos/{hooklib.CHANNEL_REPO}/issues?state=open&labels=stop&per_page=10")
        issues = [i["number"] for i in items if "pull_request" not in i]
    except Exception as e:  # fail-open  # noqa: BLE001
        hooklib.log_stderr(f"kill-switch: GitHub unreachable ({type(e).__name__}); allowing step")
        return None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"at": time.time(), "issues": issues}))
    except Exception:  # noqa: BLE001, S110
        pass
    return issues


def decide(root: Path) -> tuple[bool, str]:
    if (root / ".kiro" / "STOP").exists():
        return True, ".kiro/STOP exists"
    issues = open_stop_issues(root)
    if issues:
        return True, f"open stop issue(s) in {hooklib.CHANNEL_REPO}: " + ", ".join(f"#{n}" for n in issues)
    return False, "no stop signal" + (" (GitHub unreachable, fail-open)" if issues is None else "")


def main() -> int:
    if "--check" not in sys.argv:
        hooklib.read_payload()  # drain stdin; the decision does not depend on it
    blocked, why = decide(hooklib.repo_root())
    if blocked:
        hooklib.log_stderr(f"KILL SWITCH: {why}. Halting. Close the stop issue / remove .kiro/STOP (humans only) to resume.")
        return BLOCK
    if "--check" in sys.argv:
        print(f"kill-switch: allow ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
