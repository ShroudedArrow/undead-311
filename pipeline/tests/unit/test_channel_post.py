"""channel-status hook (scripts/channel_post.py): the status line names the run and the step.

No spec requirement covers the hooks; this backs the ops#6 finding (run smoke-2), where the hook posted "task ?: (finished)".
GitHub is never called: hooklib.gh_request is replaced by a recorder.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import channel_post
import hooklib

# A PostTaskExec-style payload from a workflow step (field names vary by surface; this uses nested spellings).
SAMPLE_PAYLOAD = {
    "hook_event_name": "PostTaskExec",
    "session_id": "sess_2941a7cd",
    "workflow": {"workflowId": "wf_7e2703967ec25e5b", "inputs": {"run_id": "smoke-2"}, "step": {"id": "validate"}},
    "task": {"title": "Run the hello gate", "status": "completed"},
}
# What smoke-2 actually sent: nothing that names the task, run or step.
EMPTY_PAYLOAD = {"hook_event_name": "PostTaskExec", "session_id": "sess_2941a7cd"}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    runs = tmp_path / ".kiro" / "workflow-runs"
    for rid, issue in (("smoke-2", 6), ("other-run", 9)):
        (runs / rid).mkdir(parents=True)
        (runs / rid / "channel.json").write_text(json.dumps({"issue": issue, "url": f"https://x/{issue}"}))
    os.utime(runs / "other-run" / "channel.json", (1_000, 1_000))  # smoke-2 is the newest run
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(hooklib, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(hooklib, "gh_request", lambda method, path, body=None: posts.append((path, body)))
    monkeypatch.delenv("KIRO_RUN_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["channel_post.py"])
    return tmp_path, posts


def post(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert channel_post.main() == 0


def test_sample_payload_names_run_and_step(repo, monkeypatch):
    _, posts = repo
    post(monkeypatch, SAMPLE_PAYLOAD)
    (path, body), = posts
    assert path.endswith("/issues/6/comments")
    assert "**Summary** run smoke-2, step validate: Run the hello gate (completed)" in body["body"]
    assert "run: smoke-2\n" in body["body"]
    assert "?" not in body["body"].split("**Summary**")[1].split("\n")[0]


def test_payload_run_id_picks_that_runs_issue(repo, monkeypatch):
    _, posts = repo
    post(monkeypatch, {"run_id": "other-run", "step_id": "review"})
    (path, body), = posts
    assert path.endswith("/issues/9/comments")
    assert "run other-run, step review: (finished)" in body["body"]


def test_payload_run_without_run_folder_posts_nothing(repo, monkeypatch):
    _, posts = repo
    post(monkeypatch, {"run_id": "no-such-run", "step_id": "review"})
    assert posts == []


def test_missing_fields_fall_back_to_the_run_folder_current_step(repo, monkeypatch):
    root, posts = repo
    (root / ".kiro" / "workflow-runs" / "smoke-2" / "current_step").write_text("implement\n")
    post(monkeypatch, EMPTY_PAYLOAD)
    (path, body), = posts
    assert path.endswith("/issues/6/comments")
    assert "run smoke-2, step implement: (finished)" in body["body"]


def test_without_current_step_the_newest_step_file_is_named(repo, monkeypatch):
    root, posts = repo
    run = root / ".kiro" / "workflow-runs" / "smoke-2"
    (run / "setup.json").write_text("{}")
    (run / "RUNNING").write_text("")
    os.utime(run / "setup.json", (5_000, 5_000))
    (run / "hello-gate.json").write_text("{}")
    os.utime(run / "hello-gate.json", (6_000, 6_000))
    os.utime(run / "RUNNING", (9_000, 9_000))  # bookkeeping files are ignored even when newer
    post(monkeypatch, EMPTY_PAYLOAD)
    (_, body), = posts
    assert "run smoke-2, step after hello-gate.json: (finished)" in body["body"]


def test_only_payload_key_names_are_saved(repo, monkeypatch):
    root, _ = repo
    post(monkeypatch, SAMPLE_PAYLOAD)
    saved = (root / ".local-data" / "channel_status_payload_keys.json").read_text()
    assert "workflow" in saved and "run_id" in saved
    assert "smoke-2" not in saved and "Run the hello gate" not in saved
