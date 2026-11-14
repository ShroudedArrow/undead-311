"""scripts/check_trailers.py exemptions (ops#125 owner decision): owner-authored and merge commits are skipped, agent commits
without trailers still fail. Requirement: structure.md commit trailers; RUN_PROTOCOL.md."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_trailers.py"
spec = importlib.util.spec_from_file_location("check_trailers", SCRIPT)
ct = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(ct)  # type: ignore[union-attr]

AGENT = ("Kiro Agent", "244629292+kiro-agent@users.noreply.github.com")
OWNER = ("ShroudedArrow", "316350912+ShroudedArrow@users.noreply.github.com")


def git(cwd: Path, *args: str, who: tuple[str, str] = AGENT) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1], "GIT_COMMITTER_NAME": who[0],
           "GIT_COMMITTER_EMAIL": who[1], "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}  # fmt: skip
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def run_check(repo: Path, rng: str, monkeypatch: pytest.MonkeyPatch, *extra: str) -> int:
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["check_trailers.py", rng, *extra])
    return ct.main()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "root")
    return tmp_path


def commit(repo: Path, msg: str, who: tuple[str, str], *trailers: str) -> None:
    args = ["commit", "-q", "--allow-empty", "-m", msg]
    for t in trailers:
        args += ["--trailer", t]
    git(repo, *args, who=who)


def test_ops125_is_owner_matches_the_owner_account_and_never_an_agent():
    assert ct.is_owner(*OWNER) and ct.is_owner("ShroudedArrow", "x@y.z")
    assert ct.is_owner("someone", "1+ShroudedArrow@users.noreply.github.com")
    assert not ct.is_owner(*AGENT) and not ct.is_owner("Kiro", "kiro@users.noreply.github.com")
    assert not ct.is_owner("NotShroudedArrow", "a@b.c")


def test_ops125_an_owner_authored_commit_without_trailers_is_exempt(repo, monkeypatch):
    commit(repo, "Update methods.md", OWNER)
    assert run_check(repo, "main~1..main", monkeypatch) == 0


def test_ops125_an_agent_commit_without_trailers_still_fails(repo, monkeypatch):
    commit(repo, "feat: agent work without trailers", AGENT)
    assert run_check(repo, "main~1..main", monkeypatch) == 1


def test_ops125_an_agent_commit_with_the_wrong_run_still_fails_and_the_right_run_passes(repo, monkeypatch):
    commit(repo, "feat: a", AGENT, "Kiro-Agent: engine", "Kiro-Run: build-1")
    assert run_check(repo, "main~1..main", monkeypatch, "--require-run", "build-2") == 1
    assert run_check(repo, "main~1..main", monkeypatch, "--require-run", "build-1") == 0


def test_ops125_a_merge_commit_is_exempt(repo, monkeypatch):
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, "feat: side work", AGENT, "Kiro-Agent: engine", "Kiro-Run: build-2")
    git(repo, "checkout", "-q", "main")
    commit(repo, "feat: main work", AGENT, "Kiro-Agent: engine", "Kiro-Run: build-2")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge side into main", "side")  # no trailers on the merge
    assert run_check(repo, "main~2..main", monkeypatch, "--require-run", "build-2") == 0
