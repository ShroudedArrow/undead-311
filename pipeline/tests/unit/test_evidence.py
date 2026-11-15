"""Evidence commands (REQ-OPS-EVID.1): `make channel-export`, `make trace`, `make kiro-stats`.

No network: the channel export runs against a fake fetch function or a stubbed urlopen. The stats test builds a small git
repository in a temporary directory."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import examples
from hypothesis import given, settings
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import channel_export
import kiro_stats

# scripts/trace.py shares its name with the standard library module, so it is loaded by path.
_spec = importlib.util.spec_from_file_location("trace_script", REPO / "scripts" / "trace.py")
trace_script = importlib.util.module_from_spec(_spec)
sys.modules["trace_script"] = trace_script
_spec.loader.exec_module(trace_script)

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


# ---------------------------------------------------------------- channel export


def fake_channel(issues: list[dict], comments: dict[int, list[dict]]):
    """A GET-only fake of the GitHub issues API that honours per_page and page."""
    calls: list[str] = []

    def fetch(path: str):
        calls.append(path)
        base, _, query = path.partition("?")
        params = dict(kv.split("=") for kv in query.split("&"))
        per, page = int(params["per_page"]), int(params["page"])
        if base.endswith("/issues"):
            rows = issues
        else:
            rows = comments.get(int(base.split("/")[-2]), [])
        return rows[(page - 1) * per: page * per]

    return fetch, calls


def issue(n: int, body: str = "body", comments: int = 0, **extra) -> dict:
    return {"number": n, "title": f"Issue {n}", "state": "open", "body": body, "comments": comments,
            "labels": [{"name": "to:engine"}, {"name": "type:finding"}], "user": {"login": "kiro-agent"},
            "created_at": "2026-11-12T10:00:00Z", **extra}


def test_export_collects_issues_comments_and_skips_pull_requests():
    """REQ-OPS-EVID.1: all pages of issues and comments, pull requests left out, ordered by number."""
    issues = [issue(n, comments=1 if n == 2 else 0) for n in range(150, 0, -1)] + [issue(999, pull_request={"url": "x"})]
    comments = {2: [{"id": 1, "body": "first comment", "user": {"login": "owner"}, "created_at": "2026-11-13T09:00:00Z"}]}
    fetch, calls = fake_channel(issues, comments)
    got = channel_export.collect(fetch, "o/r")
    assert [i["number"] for i in got] == list(range(1, 151))
    assert got[1]["_comments"][0]["body"] == "first comment"
    assert any("page=2" in c for c in calls)  # 150 issues need a second page
    text = channel_export.render(got, "o/r")
    assert "## #1 Issue 1" in text and "first comment" in text and "#999" not in text


def test_export_is_deterministic():
    """REQ-OPS-EVID.1: the same channel gives byte-identical text."""
    fetch, _ = fake_channel([issue(2), issue(1)], {})
    a = channel_export.render(channel_export.collect(fetch, "o/r"), "o/r")
    fetch, _ = fake_channel([issue(1), issue(2)], {})
    assert a == channel_export.render(channel_export.collect(fetch, "o/r"), "o/r")


@settings(max_examples=examples(60))
@given(before=st.text(max_size=40), after=st.text(max_size=40))
def test_the_token_never_reaches_the_output(before, after):
    """REQ-OPS-EVID.1: whatever the issue text contains, the run-time token is not written out."""
    secret = "s3cr3t-run-time-value"
    body = f"{before}{secret}{after} Authorization: Bearer {TOKEN}"
    text = channel_export.render([issue(1, body=body, title=f"t {secret}")], "o/r", secret)
    assert secret not in text
    assert TOKEN not in text


@pytest.mark.parametrize("shape", [TOKEN, "github_pat_" + "x" * 30, "xoxb-1234567890-abcdef", "AKIA" + "A" * 16, "Bearer " + "z" * 30])
def test_credential_shapes_are_redacted(shape):
    """REQ-OPS-EVID.1: credential-shaped text is removed even when it is not the run-time token."""
    assert shape not in channel_export.redact(f"see {shape} here")


def test_without_a_token_nothing_is_written(tmp_path, monkeypatch, capsys):
    """REQ-OPS-EVID.1: no token means exit 2 and no file, so an empty export never replaces a real one."""
    monkeypatch.delenv("GITHUB_CHANNEL_READ_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_CHANNEL_TOKEN", raising=False)
    out = tmp_path / "AGENT_CHANNEL.md"
    out.write_text("old export", encoding="utf-8")
    assert channel_export.main(["--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "old export"
    assert "GITHUB_CHANNEL_READ_TOKEN" in capsys.readouterr().err


def test_a_failed_read_keeps_the_old_export(tmp_path, capsys):
    """REQ-OPS-EVID.1: a network or shape error exits 1, keeps the old file and does not print the token."""
    def boom(path: str):
        raise OSError(f"connection reset while sending {TOKEN}")

    out = tmp_path / "x.md"
    out.write_text("old", encoding="utf-8")
    assert channel_export.main(["--out", str(out)], fetch=boom, env_token=TOKEN) == 1
    assert out.read_text(encoding="utf-8") == "old"
    assert TOKEN not in capsys.readouterr().err


def test_requests_are_get_only_and_carry_the_token(monkeypatch):
    """REQ-OPS-EVID.1: the read-only token is used for GET requests, in the Authorization header only."""
    seen = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[]"

    def fake_urlopen(req, timeout=None):
        seen.append((req.get_method(), req.full_url, req.get_header("Authorization"), req.data))
        return Resp()

    monkeypatch.setattr(channel_export.urllib.request, "urlopen", fake_urlopen)
    channel_export.collect(channel_export.make_fetch(TOKEN), "o/r")
    assert seen and all(m == "GET" and d is None and TOKEN not in url for m, url, _, d in seen)
    assert all(h == f"Bearer {TOKEN}" for _, _, h, _ in seen)


def test_main_writes_the_file(tmp_path):
    """REQ-OPS-EVID.1: the export lands in the output file with the token redacted."""
    fetch, _ = fake_channel([issue(1, body=f"oops {TOKEN}")], {})
    out = tmp_path / "docs" / "AGENT_CHANNEL.md"
    assert channel_export.main(["--out", str(out)], fetch=fetch, env_token=TOKEN) == 0
    text = out.read_text(encoding="utf-8")
    assert "## #1 Issue 1" in text and TOKEN not in text


# ---------------------------------------------------------------- trace


def make_repo(tmp_path: Path) -> Path:
    spec = tmp_path / ".kiro" / "specs" / "demo"
    spec.mkdir(parents=True)
    (spec / "requirements.md").write_text(
        "### REQ-A-1: Alpha\n**Layer:** demo-critical\n1. x\n\n### REQ-B: Beta\n**Layer:** delight\n1. y\n\n"
        "### REQ-C: Gamma\n\n### REQ-D: Delta\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text('"""Implements REQ-A-1.2 and REQ-B."""\n', encoding="utf-8")
    (tmp_path / "scripts" / "c.py").write_text("# REQ-C.1\n# REQ-UNKNOWN-9\n", encoding="utf-8")
    t = tmp_path / "pipeline" / "tests" / "unit"
    t.mkdir(parents=True)
    (t / "test_a.py").write_text("def test_alpha_req_a_1():\n    '''REQ-A-1.2'''\n", encoding="utf-8")
    (t / "test_d.py").write_text("# REQ-D.1\n", encoding="utf-8")
    return tmp_path


def test_trace_statuses(tmp_path):
    """REQ-OPS-EVID.1: tested, untested, test-only and uncited are told apart; sub-numbers count for the requirement."""
    root = make_repo(tmp_path)
    text, states = trace_script.build(root)
    assert states == {"REQ-A-1": "tested", "REQ-B": "untested", "REQ-C": "untested", "REQ-D": "test-only"}
    assert "REQ-UNKNOWN-9" in text  # cited but undefined IDs are listed
    assert "| REQ-A-1 Alpha | demo | demo-critical |" in text


def test_trace_is_deterministic_and_main_writes(tmp_path):
    """REQ-OPS-EVID.1: same tree, same file."""
    root = make_repo(tmp_path)
    assert trace_script.main(["--root", str(root), "--out", "docs/T.md"]) == 0
    first = (root / "docs" / "T.md").read_text(encoding="utf-8")
    assert trace_script.build(root)[0] == first


@given(a=st.booleans(), b=st.booleans())
def test_trace_status_is_a_function_of_code_and_tests(a, b):
    """REQ-OPS-EVID.1: four states, one per combination."""
    assert trace_script.status(a, b) == {(True, True): "tested", (True, False): "untested",
                                         (False, True): "test-only", (False, False): "uncited"}[(a, b)]


def test_trace_covers_every_requirement_of_the_repo():
    """REQ-OPS-EVID.1: on this repo, every requirement heading appears in the table."""
    text, states = trace_script.build(REPO)
    assert len(states) > 50
    assert all(rid in text for rid in states)


# ---------------------------------------------------------------- kiro-stats


def git(cwd: Path, *args: str, author: str = "Kiro Agent", email: str = "agent@example.com") -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": author,
           "GIT_COMMITTER_EMAIL": email, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def commit(cwd: Path, files: dict[str, str], msg: str, *trailers: str, **kw) -> None:
    for rel, text in files.items():
        p = cwd / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(cwd, "add", "-A", **kw)
    args = ["commit", "-q", "-m", msg]
    for t in trailers:
        args += ["--trailer", t]
    git(cwd, *args, **kw)


def test_stats_per_agent_and_run(tmp_path):
    """REQ-OPS-EVID.1: commits, files and tests are counted per Kiro-Agent and per Kiro-Run; merges are left out."""
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, {"pipeline/tests/unit/test_x.py": "def test_a():\n    pass\n\ndef test_b():\n    pass\n", "a.py": "x=1\n"},
           "feat: x", "Kiro-Agent: engine", "Kiro-Run: build-1")
    commit(tmp_path, {"web/src/a.test.ts": "it('a', () => {});\ntest('b', () => {});\nconst it2 = 1;\n"},
           "feat: y", "Kiro-Agent: web", "Kiro-Run: build-1")
    commit(tmp_path, {"b.py": "y=2\n"}, "fix: z", "Kiro-Agent: engine", "Kiro-Run: build-2")
    commit(tmp_path, {"c.py": "z=3\n"}, "docs: by hand", author="ShroudedArrow", email="1+ShroudedArrow@users.noreply.github.com")
    commit(tmp_path, {"d.py": "w=4\n"}, "oops: no trailers")
    git(tmp_path, "checkout", "-q", "-b", "side")
    commit(tmp_path, {"e.py": "v=5\n"}, "feat: side", "Kiro-Agent: engine", "Kiro-Run: build-2")
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "--no-ff", "-q", "-m", "merge side", "side")

    commits = kiro_stats.parse(subprocess.run(
        ["git", "log", "--no-merges", "--no-renames", "-p", "-U0",
         "--format=" + kiro_stats.RECORD + kiro_stats.FIELD.join(["%H", "%an", "%ae", "%(trailers:key=Kiro-Agent,valueonly,unfold,separator=%x2c)",
                                                                   "%(trailers:key=Kiro-Run,valueonly,unfold,separator=%x2c)"]), "HEAD"],
        cwd=tmp_path, capture_output=True, text=True, check=True).stdout)
    by_agent, by_run = kiro_stats.tally(commits)
    assert len(commits) == 6  # the merge is not counted
    assert (by_agent["engine"].commits, len(by_agent["engine"].files), by_agent["engine"].tests) == (3, 4, 2)
    assert (by_agent["web"].commits, by_agent["web"].tests) == (1, 2)
    assert by_agent["owner"].commits == 1
    assert by_agent[kiro_stats.NO_TRAILER].commits == 1
    assert by_run["build-1"].commits == 2 and by_run["build-2"].commits == 2
    assert sum(t.commits for t in by_agent.values()) == sum(t.commits for t in by_run.values()) == 6


def test_stats_partition_the_real_history():
    """REQ-OPS-EVID.1: every non-merge commit is counted under exactly one agent and one run (a partition)."""
    commits = kiro_stats.parse(kiro_stats.read_log("HEAD"))
    by_agent, by_run = kiro_stats.tally(commits)
    expected = int(subprocess.run(["git", "rev-list", "--no-merges", "--count", "HEAD"], cwd=REPO, capture_output=True,
                                  text=True, check=True).stdout)
    assert len(commits) == expected
    assert sum(t.commits for t in by_agent.values()) == expected
    assert sum(t.commits for t in by_run.values()) == expected
    text = kiro_stats.render(commits)
    assert "## Per agent" in text and "## Per workflow run" in text


@given(path=st.sampled_from(["pipeline/tests/unit/test_a.py", "web/src/x.test.tsx", "web/e2e/a.spec.ts", "pipeline/undead311/a.py", "web/src/a.ts"]),
       line=st.sampled_from(["+def test_x():", "+  it('x', () => {", "+test('y', async () => {", "+x = 1", "+// it("]))
def test_only_test_files_count_tests(path, line):
    """REQ-OPS-EVID.1: a test is counted only in a test file, and only when the line starts one."""
    n = kiro_stats.count_tests(path, line)
    assert n in (0, 1)
    is_test_file = kiro_stats.TEST_FILE.search(path) is not None
    if not is_test_file:
        assert n == 0
