"""Open (or reuse) the run-log issue for a workflow run and write channel.json. Standard library only.

Fallback for the github-channel MCP server: if the MCP server is not available in a session, workflow step 0
runs this instead. Title `Run <run_id>: <recipe>`, label `type:status`, body in the agent-channel.md format.
Usage: python3 scripts/channel_open.py --run-id R --recipe NAME [--close] [--comment TEXT]
  --close    post the final comment (if given) and close the run-log issue
Writes .kiro/workflow-runs/<run_id>/channel.json = {"issue": N, "url": "...", "repo": "..."}.
Exits 0 even when GitHub is unreachable (channel.json then records the error); the channel never blocks a run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hooklib


def body(run_id: str, recipe: str) -> str:
    return (
        f"```yaml\nfrom: workflow\nto: human\ntype: status\nrun: {run_id}\nrefs: [.kiro/workflows/{recipe}.workflow.yaml]\n```\n"
        f"**Summary** Run log for `{recipe}` run `{run_id}`. Each step posts one comment here.\n\n"
        "**Evidence** Run artifacts live in `.kiro/workflow-runs/" + run_id + "/`.\n\n"
        "**Requested action** none. To halt the run, open an issue labeled `stop` in this repo."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--close", action="store_true")
    ap.add_argument("--comment")
    a = ap.parse_args()
    root = hooklib.repo_root()
    run_dir = root / ".kiro" / "workflow-runs" / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ch_path = run_dir / "channel.json"
    repo = hooklib.CHANNEL_REPO
    try:
        ch = json.loads(ch_path.read_text()) if ch_path.exists() else {}
        if not ch.get("issue"):
            title = f"Run {a.run_id}: {a.recipe}"
            found = [i for i in hooklib.gh_request("GET", f"/repos/{repo}/issues?state=all&labels=type:status&per_page=50")
                     if i.get("title") == title]
            issue = found[0] if found else hooklib.gh_request(
                "POST", f"/repos/{repo}/issues", {"title": title, "body": body(a.run_id, a.recipe), "labels": ["type:status"]})
            ch = {"issue": issue["number"], "url": issue["html_url"], "repo": repo}
            ch_path.write_text(json.dumps(ch, indent=2) + "\n")
        if a.comment:
            hooklib.gh_request("POST", f"/repos/{repo}/issues/{ch['issue']}/comments", {"body": a.comment})
        if a.close:
            hooklib.gh_request("PATCH", f"/repos/{repo}/issues/{ch['issue']}", {"state": "closed"})
        print(json.dumps(ch))
    except Exception as e:  # noqa: BLE001 - the channel must never block a run
        hooklib.log_stderr(f"channel_open: GitHub not reachable ({type(e).__name__}); continuing without the channel")
        if not ch_path.exists():
            ch_path.write_text(json.dumps({"issue": None, "error": type(e).__name__}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
