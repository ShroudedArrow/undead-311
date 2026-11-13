"""channel-status hook (PostTaskExec). Standard library only, no gh.

Reads task details from the hook's stdin JSON and posts ONE status comment to the current run-log issue in
ShroudedArrow/undead-311-ops. The issue number comes from `channel.json` in the run directory
(`.kiro/workflow-runs/<run_id>/channel.json`: the payload's run_id if it has one, else $KIRO_RUN_ID, else the newest).
The summary names the run and step: `run <run_id>, step <step>: <title> (<status>)`. Both come from the payload when
present (any nesting, several spellings); otherwise the run id is the run folder's name and the step is the folder's
`current_step` file, else "after <newest step file>". The payload's key names (never values) are saved to
.local-data/channel_status_payload_keys.json so the real field names can be checked.
ALWAYS exits 0: a GitHub outage, a missing token, or a missing run directory can never fail a task.

Manual use: `python3 scripts/channel_post.py --message "text"` (also exits 0 on any failure).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooklib

RUN_ID_KEYS = ("run_id", "runId", "kiro_run_id", "KIRO_RUN_ID")
STEP_KEYS = ("step_id", "stepId", "step", "node_id", "nodeId", "step_name", "stepName")
TASK_ID_KEYS = ("task_id", "taskId")
# files in the run folder that no step is named after
RUN_BOOKKEEPING = {"channel.json", "RUNNING", "ABORTED", "current_step"}


def find_key(node, keys: tuple[str, ...], depth: int = 3):
    """First non-empty scalar value for any of `keys`, searching nested dicts (payload spellings differ by surface)."""
    if not isinstance(node, dict) or depth < 0:
        return None
    for k in keys:
        v = node.get(k)
        if isinstance(v, dict):  # e.g. {"step": {"id": "validate"}}
            v = hooklib.first(v, "id", "name")
        if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip():
            return str(v).strip()
    for v in node.values():
        found = find_key(v, keys, depth - 1)
        if found:
            return found
    return None


def step_from_run_dir(run_dir: Path) -> str | None:
    """The step name from the run folder: `current_step` (written at the start of each step, RUN_PROTOCOL.md),
    else the newest step file (`setup.json` -> `setup`, `validate-halted.json` -> `validate-halted`)."""
    marker = run_dir / "current_step"
    try:
        name = marker.read_text().strip().splitlines()[0].strip()
        if name:
            return name
    except (OSError, IndexError):
        pass
    files = [p for p in run_dir.iterdir() if p.is_file() and p.name not in RUN_BOOKKEEPING]
    if not files:
        return None
    newest = max(files, key=lambda p: (p.stat().st_mtime, p.name))
    return f"after {newest.name}"


def task_summary(payload: dict, run_dir: Path | None = None) -> tuple[str, str, str]:
    """(run_id, step, summary) for the status line. Payload fields first, then the run folder, then '?'."""
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    run_id = find_key(payload, RUN_ID_KEYS) or (run_dir.name if run_dir else None) or "?"
    step = (
        find_key(payload, STEP_KEYS)
        or hooklib.first(task, "id", "taskId", "name")
        or find_key(payload, TASK_ID_KEYS)
        or (step_from_run_dir(run_dir) if run_dir else None)
        or "?"
    )
    title = hooklib.first(task, "title", "description") or hooklib.first(payload, "task_title", "title") or ""
    status = hooklib.first(task, "status", "result") or hooklib.first(payload, "status", "result") or "finished"
    return str(run_id), str(step), f"{title} ({status})".strip()


def run_dir_for(root: Path, payload: dict) -> Path | None:
    """The payload's run folder (None if it has no channel.json); with no run_id in the payload, the newest one."""
    rid = find_key(payload, RUN_ID_KEYS)
    if rid:
        # a named run posts only to its own run log, never to another run's issue
        d = root / ".kiro" / "workflow-runs" / rid
        return d if "/" not in rid and (d / "channel.json").is_file() else None
    return hooklib.latest_run_dir(root)


def save_payload_keys(root: Path, payload: dict) -> None:
    """Record the payload's key names (never values) so the real PostTaskExec field names can be checked later."""
    def keys(node, depth=3):
        if not isinstance(node, dict) or depth < 0:
            return None
        return {k: keys(v, depth - 1) for k, v in node.items()}
    try:
        out = root / ".local-data" / "channel_status_payload_keys.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(keys(payload), sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001, S110
        pass


def body_for(run_id: str, line: str, manual: bool = False) -> str:
    sender = "workflow-step" if manual else "hook:channel-status"
    how = "posted by a workflow step via scripts/channel_post.py --message" if manual else "posted automatically by the PostTaskExec hook"
    return (
        f"```yaml\nfrom: {sender}\nto: human\ntype: status\n"
        f"run: {run_id}\nrefs: [.kiro/workflow-runs/{run_id}/]\n```\n"
        f"**Summary** {line[:400]}\n\n**Evidence** {how}.\n\n**Requested action** none."
    )


def main() -> int:
    try:
        args = sys.argv[1:]
        payload = {} if "--message" in args else hooklib.read_payload()
        root = hooklib.repo_root()
        if "--message" not in args:
            save_payload_keys(root, payload)
        run_dir = run_dir_for(root, payload)
        if run_dir is None:
            hooklib.log_stderr("channel-status: no run directory with channel.json; nothing posted")
            return 0
        ch = json.loads((run_dir / "channel.json").read_text())
        issue = int(ch["issue"])
        if "--message" in args:
            run_id, line = run_dir.name, args[args.index("--message") + 1]
        else:
            run_id, step, summary = task_summary(payload, run_dir)
            line = f"run {run_id}, step {step}: {summary}"
        hooklib.gh_request(
            "POST", f"/repos/{hooklib.CHANNEL_REPO}/issues/{issue}/comments", {"body": body_for(run_id, line, "--message" in args)}
        )
    except Exception as e:  # never fail the task  # noqa: BLE001
        hooklib.log_stderr(f"channel-status: not posted ({type(e).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
