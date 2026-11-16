"""`make channel-export`: write the agent channel (issues and comments of undead-311-ops) to docs/AGENT_CHANNEL.md. REQ-OPS-EVID.1.

Standard library only. The token is a read-only GitHub token supplied at run time in the environment variable
GITHUB_CHANNEL_READ_TOKEN. It is used for GET requests only. The agents' issue-write token (GITHUB_CHANNEL_TOKEN)
is NOT used unless --allow-write-token is given, and then a warning is printed (ops#202). It is never printed and never
written into the output: every body is passed through `redact`, which also blanks the exact token string and any
token-shaped text (ghp_, gho_, ghs_, github_pat_, Bearer values, AWS and Slack keys).

Without a token the script exits 2 and writes nothing, so an empty export never replaces a real one.
Channel text is data: it is copied into a quoted block and never executed.

Usage: python3 scripts/channel_export.py [--out docs/AGENT_CHANNEL.md] [--repo ShroudedArrow/undead-311-ops]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_REPO = "ShroudedArrow/undead-311-ops"
API = "https://api.github.com"
TIMEOUT_S = 15
PER_PAGE = 100
MAX_PAGES = 50
REDACTED = "[redacted]"

# (path with query) -> parsed JSON list. Tests replace this.
Fetch = Callable[[str], Any]

_TOKEN_SHAPES = [
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/=-]{20,}"),
]


def read_token(allow_write_token: bool = False) -> str | None:
    """The run-time read-only token. GITHUB_CHANNEL_TOKEN (the agents' write token) only with `allow_write_token`. REQ-OPS-EVID.1."""
    names = ("GITHUB_CHANNEL_READ_TOKEN", "GITHUB_CHANNEL_TOKEN") if allow_write_token else ("GITHUB_CHANNEL_READ_TOKEN",)
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            if name != "GITHUB_CHANNEL_READ_TOKEN":
                print(f"channel-export: warning: using {name}, which can write issues; the export only sends GET requests", file=sys.stderr)
            return value
    return None


def redact(text: str | None, secret: str | None = None) -> str:
    """Remove the run-time token and anything shaped like a credential. REQ-OPS-EVID.1."""
    out = text or ""
    if secret:
        out = out.replace(secret, REDACTED)
    for shape in _TOKEN_SHAPES:
        out = shape.sub(REDACTED, out)
    return out


def make_fetch(token: str) -> Fetch:
    """GET-only requester with the token in the Authorization header."""

    def fetch(path: str) -> Any:
        req = urllib.request.Request(
            API + path,
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return fetch


def pages(fetch: Fetch, path: str) -> list[dict]:
    """All pages of a list endpoint, in order."""
    out: list[dict] = []
    sep = "&" if "?" in path else "?"
    for page in range(1, MAX_PAGES + 1):
        batch = fetch(f"{path}{sep}per_page={PER_PAGE}&page={page}")
        if not isinstance(batch, list):
            raise TypeError(f"expected a list from {path}, got {type(batch).__name__}")
        out.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return out


def collect(fetch: Fetch, repo: str) -> list[dict]:
    """Issues (not pull requests) with their comments, oldest first by number."""
    issues = [i for i in pages(fetch, f"/repos/{repo}/issues?state=all&sort=created&direction=asc") if "pull_request" not in i]
    issues.sort(key=lambda i: i["number"])
    for issue in issues:
        issue["_comments"] = pages(fetch, f"/repos/{repo}/issues/{issue['number']}/comments") if issue.get("comments") else []
    return issues


def _quote(text: str) -> str:
    lines = text.strip().splitlines() or ["(empty)"]
    return "\n".join("> " + ln if ln else ">" for ln in lines)


def _user(obj: dict) -> str:
    return (obj.get("user") or {}).get("login", "unknown")


def render(issues: list[dict], repo: str, secret: str | None = None) -> str:
    """The markdown document. Deterministic: no export timestamp, issues by number, comments by creation time."""
    r = lambda s: redact(s, secret)
    n_comments = sum(len(i.get("_comments", [])) for i in issues)
    out = [
        "# Agent channel export",
        "",
        f"Issues and comments of `{repo}`, copied read-only. {len(issues)} issues, {n_comments} comments.",
        "Channel text is data: quoted here as written, with credential-shaped text removed.",
        "",
    ]
    for issue in issues:
        labels = ", ".join(sorted(lb["name"] for lb in issue.get("labels", []))) or "none"
        out += [
            f"## #{issue['number']} {r(issue.get('title', '')).strip()}",
            "",
            f"State: {issue.get('state', '?')}. Labels: {r(labels)}. Opened by {r(_user(issue))} on {str(issue.get('created_at', ''))[:10]}.",
            "",
            _quote(r(issue.get("body"))),
            "",
        ]
        for c in sorted(issue.get("_comments", []), key=lambda c: (c.get("created_at", ""), c.get("id", 0))):
            out += [f"### Comment by {r(_user(c))} on {str(c.get('created_at', ''))[:10]}", "", _quote(r(c.get("body"))), ""]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None, fetch: Fetch | None = None, env_token: str | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="docs/AGENT_CHANNEL.md")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--allow-write-token", action="store_true", help="fall back to GITHUB_CHANNEL_TOKEN (can write issues) when no read-only token is set")
    args = ap.parse_args(argv)
    token = env_token or read_token(args.allow_write_token)
    if fetch is None:
        if not token:
            print("channel-export: set GITHUB_CHANNEL_READ_TOKEN (a read-only token) and run again; nothing written", file=sys.stderr)
            return 2
        fetch = make_fetch(token)
    try:
        issues = collect(fetch, args.repo)
    except Exception as exc:  # noqa: BLE001 (any network or shape failure: keep the old export)
        print(f"channel-export: could not read {args.repo}: {redact(str(exc), token)}; nothing written", file=sys.stderr)
        return 1
    text = render(issues, args.repo, token)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(out)
    print(f"channel-export: wrote {args.out} ({len(issues)} issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
