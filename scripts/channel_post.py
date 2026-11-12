"""channel-status hook (PostTaskExec). Standard library only, no gh.

Reads task details from the hook's stdin JSON and posts ONE status comment to the current run-log issue in
ShroudedArrow/undead-311-ops. The issue number comes from `channel.json` in the run directory
(`.kiro/workflow-runs/<run_id>/channel.json`, newest one unless $KIRO_RUN_ID is set).
ALWAYS exits 0: a GitHub outage, a missing token, or a missing run directory can never fail a task.

Manual use: `python3 scripts/channel_post.py --message "text"` (also exits 0 on any failure).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooklib


def task_summary(payload: dict) -> tuple[str, str]:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    tid = hooklib.first(task, "id", "taskId") or hooklib.first(payload, "task_id", "taskId") or "?"
    title = hooklib.first(task, "title", "name", "description") or hooklib.first(payload, "task_title", "title") or ""
    status = hooklib.first(task, "status", "result") or hooklib.first(payload, "status", "result") or "finished"
    return str(tid), f"{title} ({status})".strip()


def body_for(run_id: str, line: str) -> str:
    return (
        "```yaml\nfrom: hook:channel-status\nto: human\ntype: status\n"
        f"run: {run_id}\nrefs: [.kiro/workflow-runs/{run_id}/]\n```\n"
        f"**Summary** {line[:400]}\n\n**Evidence** posted automatically by the PostTaskExec hook.\n\n**Requested action** none."
    )


def main() -> int:
    try:
        args = sys.argv[1:]
        payload = {} if "--message" in args else hooklib.read_payload()
        root = hooklib.repo_root()
        run_dir = hooklib.latest_run_dir(root)
        if run_dir is None:
            hooklib.log_stderr("channel-status: no run directory with channel.json; nothing posted")
            return 0
        ch = json.loads((run_dir / "channel.json").read_text())
        issue = int(ch["issue"])
        if "--message" in args:
            line = args[args.index("--message") + 1]
        else:
            tid, summary = task_summary(payload)
            line = f"task {tid}: {summary}"
        hooklib.gh_request(
            "POST", f"/repos/{hooklib.CHANNEL_REPO}/issues/{issue}/comments", {"body": body_for(run_dir.name, line)}
        )
    except Exception as e:  # never fail the task  # noqa: BLE001
        hooklib.log_stderr(f"channel-status: not posted ({type(e).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
