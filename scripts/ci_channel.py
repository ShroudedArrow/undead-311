"""CI to agent channel (standard library only). ALWAYS exits 0. REQ-OPS-CI.3, REQ-OPS-PBT.2, REQ-OPS-ALERT.1.

Three subcommands, all fail-open: a missing token, a 4xx or 5xx answer, a timeout or a malformed reply never fails a
build, because the channel is the audit trail and not a gate (agent-channel.md, tech.md).

  result   post ONE one-line CI result as a comment on the standing issue "CI results" (created when missing).
  finding  open (or update) a `type:finding` issue labeled `to:engine` or `to:web`, with the shrunk example
           (deep property tests, REQ-OPS-PBT.2).
  alert    open (or update) a `needs-human` issue when a nightly, CI-on-main or deep-PBT job fails (REQ-OPS-ALERT.1).

The token is read from the environment variable GITHUB_CHANNEL_TOKEN. Actions secret names cannot start with
`GITHUB_`, so each workflow maps `env: GITHUB_CHANNEL_TOKEN: ${{ secrets.CHANNEL_TOKEN }}` (design.md). The token is
never printed, logged or written into an issue body. All text that comes from the workflow (job names, URLs, example
text) is data: it is shortened, stripped of control characters and placed inside the body, never executed.

Example (ci.yml `channel` job):
  python3 scripts/ci_channel.py result --results python=success web=failure --run-url "$URL" --ref main --alert-on-main
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

CHANNEL_REPO = "ShroudedArrow/undead-311-ops"
API = "https://api.github.com"
TIMEOUT_S = 8
MAX_BODY = 3500
RESULT_ISSUE_TITLE = "CI results"
OK_STATES = {"success", "skipped"}

# (method, path, body or None) -> parsed JSON reply. Tests replace this; main() may be given any callable.
Request = Callable[[str, str, "dict | None"], Any]


def token() -> str | None:
    t = os.environ.get("GITHUB_CHANNEL_TOKEN", "").strip()
    return t or None


def api_request(method: str, path: str, body: dict | None = None) -> Any:
    """One GitHub REST call with the channel token. Raises on any failure; callers swallow it (fail-open)."""
    tok = token()
    if not tok:
        raise RuntimeError("no channel token")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "undead-311-ci",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (fixed https host)
        raw = resp.read()
    return json.loads(raw) if raw.strip() else {}


def clean(text: object, limit: int = 300) -> str:
    """Workflow-supplied text as one safe line: control characters become spaces, the length is capped."""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def parse_results(pairs: list[str]) -> dict[str, str]:
    """`python=success web=failure` -> {"python": "success", "web": "failure"}. Entries without `=` are ignored."""
    out: dict[str, str] = {}
    for p in pairs:
        name, sep, state = p.partition("=")
        if sep and name.strip():
            out[clean(name, 40)] = clean(state or "unknown", 20)
    return out


def overall(results: dict[str, str]) -> str:
    """`success` when every job succeeded or was skipped, else `failure`. No jobs at all is `failure` (nothing ran)."""
    if not results:
        return "failure"
    return "success" if all(s in OK_STATES for s in results.values()) else "failure"


def one_line(results: dict[str, str], ref: str, sha: str) -> str:
    """REQ-OPS-CI.3: the single summary line. Failed jobs are named; a green run just counts its jobs."""
    state = overall(results)
    where = clean(ref or "?", 60) + (f"@{clean(sha, 100)[:7]}" if sha else "")
    if state == "success":
        return f"CI passed on {where} ({len(results)} jobs)"
    failed = sorted(n for n, s in results.items() if s not in OK_STATES)
    return f"CI failed on {where}: {', '.join(failed) if failed else 'no job results'}"


def block(sender: str, to: str, kind: str, run: str, refs: list[str]) -> str:
    """The agent-channel.md message header."""
    return (
        "```yaml\n"
        f"from: {sender}\nto: {to}\ntype: {kind}\nrun: {clean(run, 60) or 'ci'}\n"
        f"refs: [{', '.join(clean(r, 100) for r in refs)}]\n"
        "```\n"
    )


def issue_path(suffix: str = "") -> str:
    return f"/repos/{CHANNEL_REPO}/issues{suffix}"


def find_open_issue(request: Request, title: str, label: str) -> int | None:
    """The newest open issue with exactly this title and label, or None."""
    from urllib.parse import quote

    issues = request("GET", issue_path(f"?state=open&labels={quote(label)}&per_page=100"), None)
    for it in issues if isinstance(issues, list) else []:
        if isinstance(it, dict) and it.get("title") == title and "pull_request" not in it:
            return int(it["number"])
    return None


def comment_or_create(request: Request, title: str, labels: list[str], body: str, find_label: str) -> int | None:
    """Comment on the open issue with this title, or create it. Returns the issue number or None."""
    n = find_open_issue(request, title, find_label)
    if n is None:
        made = request("POST", issue_path(), {"title": title, "labels": labels, "body": body})
        return int(made["number"]) if isinstance(made, dict) and "number" in made else None
    request("POST", issue_path(f"/{n}/comments"), {"body": body})
    return n


def post_result(request: Request, results: dict[str, str], ref: str, sha: str, run_url: str, run_id: str) -> int | None:
    """REQ-OPS-CI.3: ONE one-line comment on the standing "CI results" issue."""
    summary = one_line(results, ref, sha)
    body = (
        block("ci", "human", "status", f"ci-{run_id}" if run_id else "ci", [".github/workflows/ci.yml"])
        + f"**Summary** {summary}\n\n**Evidence** {clean(run_url, 200) or 'no run URL'}\n"
    )
    return comment_or_create(request, RESULT_ISSUE_TITLE, ["type:status"], body[:MAX_BODY], "type:status")


def post_finding(request: Request, title: str, target: str, example: str, run_url: str, run_id: str) -> int | None:
    """REQ-OPS-PBT.2: a `type:finding` issue to the engine or the web, with the shrunk example in a code fence."""
    target = target if target in {"engine", "web"} else "engine"
    full_title = f"[deep-pbt] {clean(title, 120)}"
    shrunk = example.replace("```", "'''")[:2000]
    body = (
        block("deep-pbt", target, "finding", f"ci-{run_id}" if run_id else "ci", [".github/workflows/deep-pbt.yml"])
        + f"**Summary** The nightly deep property run found a failure.\n\n**Evidence** {clean(run_url, 200)}\n\n"
        + f"```\n{shrunk}\n```\n\n**Requested action** Fix the code or the property, then close this issue with the commit link.\n"
    )
    return comment_or_create(
        request, full_title, ["type:finding", f"to:{target}"], body[:MAX_BODY], f"to:{target}"
    )


def post_alert(request: Request, title: str, detail: str, run_url: str, run_id: str) -> int | None:
    """REQ-OPS-ALERT.1: a `needs-human` issue when a nightly, CI-on-main or deep-PBT job fails."""
    full_title = f"[alert] {clean(title, 120)}"
    body = (
        block("ci", "human", "status", f"ci-{run_id}" if run_id else "ci", [])
        + f"**Summary** {clean(detail, 300)}\n\n**Evidence** {clean(run_url, 200) or 'no run URL'}\n\n"
        + "**Requested action** Look at the failed run. GitHub's own failure email is the fallback if this issue is not seen.\n"
    )
    return comment_or_create(request, full_title, ["needs-human", "type:status"], body[:MAX_BODY], "needs-human")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("result", "finding", "alert"):
        s = sub.add_parser(name)
        s.add_argument("--run-url", default=os.environ.get("RUN_URL", ""))
        s.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    r = sub.choices["result"]
    r.add_argument("--results", nargs="*", default=[], help="job=state pairs, e.g. python=success")
    r.add_argument("--ref", default=os.environ.get("GITHUB_REF_NAME", ""))
    r.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    r.add_argument("--alert-on-main", action="store_true", help="also open a needs-human alert when this is main and red")
    f = sub.choices["finding"]
    f.add_argument("--title", required=True)
    f.add_argument("--target", default="engine", choices=["engine", "web"])
    f.add_argument("--example-file", default="", help="file with the shrunk example (read, never executed)")
    a = sub.choices["alert"]
    a.add_argument("--title", required=True)
    a.add_argument("--detail", default="A scheduled job failed.")
    return p


def run(argv: list[str], request: Request = api_request) -> None:
    """Does the work; may raise. main() turns every failure into exit code 0."""
    args = build_parser().parse_args(argv)
    if args.cmd == "result":
        results = parse_results(args.results)
        post_result(request, results, args.ref, args.sha, args.run_url, args.run_id)
        if args.alert_on_main and args.ref == "main" and overall(results) == "failure":
            post_alert(request, "CI failed on main", one_line(results, args.ref, args.sha), args.run_url, args.run_id)
    elif args.cmd == "finding":
        example = ""
        if args.example_file:
            with open(args.example_file, encoding="utf-8", errors="replace") as fh:
                example = fh.read(4000)
        post_finding(request, args.title, args.target, example, args.run_url, args.run_id)
    else:
        post_alert(request, args.title, args.detail, args.run_url, args.run_id)


def main(argv: list[str] | None = None, request: Request = api_request) -> int:
    """ALWAYS returns 0 (REQ-OPS-CI.3): a failure to post never fails the build."""
    try:
        if not token() and request is api_request:
            print("ci_channel: no channel token; nothing posted", file=sys.stderr)
            return 0
        run(sys.argv[1:] if argv is None else argv, request)
    except BaseException as exc:  # noqa: BLE001 (SystemExit from argparse, KeyboardInterrupt, HTTP, timeout, bad JSON)
        print(f"ci_channel: not posted ({type(exc).__name__})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
