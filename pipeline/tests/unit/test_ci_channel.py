"""Check O2 (nightly-and-deploy design): scripts/ci_channel.py never fails a build.

REQ-OPS-CI.3: the CI posts a one-line result to the agent channel; a failure to post (no token, 4xx, 5xx, timeout, bad
reply) never fails the build, so `main` returns 0 for every one of them.
REQ-OPS-PBT.2: a deep-PBT failure opens or updates a `type:finding` issue labeled `to:engine` or `to:web`.
REQ-OPS-ALERT.1: a failed CI-on-main, nightly or deep-PBT job opens a `needs-human` issue.
GitHub is never called: requests go to a recorder, a failing stub, or a local HTTP server.
"""

from __future__ import annotations

import http.server
import json
import socket
import sys
import threading
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import ci_channel


class Recorder:
    """A fake GitHub: lists the given open issues, records every POST, numbers new issues from 900."""

    def __init__(self, open_issues: list[dict] | None = None):
        self.open_issues = open_issues or []
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            return self.open_issues
        if path.endswith("/comments"):
            return {"id": 1}
        return {"number": 900}

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch):
    monkeypatch.delenv("GITHUB_CHANNEL_TOKEN", raising=False)


# ---- O2: every failure mode exits 0 ------------------------------------------------------------------------------

def http_error(code: int):
    return urllib.error.HTTPError("https://api.github.com/x", code, "boom", {}, None)


FAILURES = {
    "http 401": http_error(401),
    "http 403": http_error(403),
    "http 404": http_error(404),
    "http 422": http_error(422),
    "http 500": http_error(500),
    "http 503": http_error(503),
    "timeout": TimeoutError("timed out"),
    "socket timeout": socket.timeout("timed out"),
    "no network": urllib.error.URLError("unreachable"),
    "os error": OSError("broken pipe"),
    "bad json": json.JSONDecodeError("bad", "x", 0),
    "key error": KeyError("number"),
}


@pytest.mark.parametrize("name", FAILURES)
@pytest.mark.parametrize("cmd", [
    ["result", "--results", "python=failure", "--ref", "main"],
    ["finding", "--title", "P5 fails"],
    ["alert", "--title", "nightly failed"],
])
def test_every_simulated_failure_exits_zero(name, cmd):
    """REQ-OPS-CI.3 (check O2): 4xx, 5xx, timeout and malformed replies are swallowed."""
    def boom(method, path, body=None):
        raise FAILURES[name]

    assert ci_channel.main(cmd, request=boom) == 0


def test_no_token_exits_zero_and_posts_nothing(capsys):
    """REQ-OPS-CI.3 (check O2): a fork PR has no secret. The default request path is skipped."""
    assert ci_channel.main(["result", "--results", "python=success"]) == 0
    assert "no channel token" in capsys.readouterr().err


def test_bad_arguments_exit_zero():
    """REQ-OPS-CI.3: even a typo in the workflow (argparse would exit 2) cannot fail the build."""
    assert ci_channel.main([], request=Recorder()) == 0
    assert ci_channel.main(["nonsense"], request=Recorder()) == 0
    assert ci_channel.main(["finding"], request=Recorder()) == 0  # --title is required


def test_missing_example_file_exits_zero():
    """REQ-OPS-PBT.2: an unreadable example file is a failure to post, not a failed build."""
    assert ci_channel.main(["finding", "--title", "t", "--example-file", "/no/such/file"], request=Recorder()) == 0


class _Handler(http.server.BaseHTTPRequestHandler):
    mode = "500"

    def _answer(self):
        if self.mode == "hang":
            threading.Event().wait(3)
            return
        self.send_response(int(self.mode))
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = do_POST = _answer

    def log_message(self, *a):  # silence the test output
        pass


@pytest.mark.parametrize("mode", ["500", "404", "hang"])
def test_a_real_http_server_failing_or_hanging_still_exits_zero(monkeypatch, mode):
    """REQ-OPS-CI.3 (check O2): the real urllib path against a local server that errors or never answers."""
    _Handler.mode = mode
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GITHUB_CHANNEL_TOKEN", "test-token")
        monkeypatch.setattr(ci_channel, "API", f"http://127.0.0.1:{server.server_address[1]}")
        monkeypatch.setattr(ci_channel, "TIMEOUT_S", 0.3)
        assert ci_channel.main(["result", "--results", "python=success"]) == 0
    finally:
        server.shutdown()


# ---- the one-line result --------------------------------------------------------------------------------------------

def test_a_green_run_posts_one_line_comment_on_the_ci_results_issue():
    """REQ-OPS-CI.3: ONE comment, a single summary line, on the standing issue (created when missing)."""
    rec = Recorder()
    ci_channel.main(["result", "--results", "python=success", "web=success", "--ref", "pr-7", "--sha", "abcdef123456",
                     "--run-url", "https://github.com/o/r/actions/runs/1"], request=rec)
    create, = rec.posts()                       # no standing issue yet: created, and the result is its body
    assert create[1].endswith("/issues") and create[2]["title"] == "CI results"
    assert "CI passed on pr-7@abcdef1 (2 jobs)" in create[2]["body"]
    assert "type:status" in create[2]["labels"]


def test_a_result_comments_on_the_existing_issue():
    """REQ-OPS-CI.3: when "CI results" is open, the line goes in as ONE comment."""
    rec = Recorder([{"number": 77, "title": "CI results"}, {"number": 78, "title": "Run x: y"}])
    ci_channel.main(["result", "--results", "python=success"], request=rec)
    (method, path, body), = rec.posts()
    assert path.endswith("/issues/77/comments")
    assert body["body"].startswith("```yaml\nfrom: ci\nto: human\ntype: status\n")


def test_a_red_run_names_the_failed_jobs():
    """REQ-OPS-CI.3: the one-line result says which jobs failed."""
    assert ci_channel.one_line({"python": "success", "budget": "failure", "axe": "cancelled"}, "main", "abc1234567") == (
        "CI failed on main@abc1234: axe, budget"
    )
    assert ci_channel.one_line({}, "main", "") == "CI failed on main: no job results"


def test_skipped_jobs_do_not_make_a_run_red():
    """REQ-OPS-CI.3."""
    assert ci_channel.overall({"python": "success", "axe": "skipped"}) == "success"
    assert ci_channel.overall({"python": "success", "axe": "cancelled"}) == "failure"


def test_alert_on_main_opens_a_needs_human_issue_only_when_red_on_main():
    """REQ-OPS-ALERT.1: CI-on-main failure alerts; a red PR and a green main do not."""
    red_main = Recorder()
    ci_channel.main(["result", "--results", "python=failure", "--ref", "main", "--alert-on-main"], request=red_main)
    assert any("needs-human" in (b or {}).get("labels", []) for _, _, b in red_main.posts())
    for results, ref in ((["python=failure"], "pr-1"), (["python=success"], "main")):
        rec = Recorder()
        ci_channel.main(["result", "--results", *results, "--ref", ref, "--alert-on-main"], request=rec)
        assert not any("needs-human" in (b or {}).get("labels", []) for _, _, b in rec.posts())


def test_an_alert_updates_the_open_alert_instead_of_opening_another():
    """REQ-OPS-ALERT.1: a second failed night comments on the open alert."""
    rec = Recorder([{"number": 55, "title": "[alert] nightly failed"}])
    ci_channel.main(["alert", "--title", "nightly failed"], request=rec)
    (_, path, _), = rec.posts()
    assert path.endswith("/issues/55/comments")


def test_a_finding_is_labeled_for_the_target_and_carries_the_example(tmp_path):
    """REQ-OPS-PBT.2: `type:finding` + `to:<target>`, with the shrunk example inside one code fence."""
    ex = tmp_path / "ex.txt"
    ex.write_text("Falsifying example: test_p5(rows=[])\n```inject```\n")
    rec = Recorder()
    ci_channel.main(["finding", "--title", "P5 fails", "--target", "web", "--example-file", str(ex)], request=rec)
    (_, _, body), = rec.posts()
    assert body["labels"] == ["type:finding", "to:web"]
    assert "Falsifying example: test_p5(rows=[])" in body["body"]
    assert body["body"].count("```") == 4          # the header fence and the example fence only
    assert body["title"] == "[deep-pbt] P5 fails"


def test_workflow_text_is_one_safe_line_and_the_token_is_never_posted(monkeypatch):
    """REQ-OPS-CI.3: untrusted text is flattened and shortened; the token never reaches a body."""
    monkeypatch.setenv("GITHUB_CHANNEL_TOKEN", "ghp_SECRET")
    rec = Recorder()
    ci_channel.main(["alert", "--title", "x\nINJECTED", "--detail", "d" * 1000, "--run-url", "http://a\r\nb"], request=rec)
    blob = json.dumps(rec.calls)
    assert "ghp_SECRET" not in blob
    assert "\\nINJECTED" not in blob and len(ci_channel.clean("y" * 1000)) == 300
