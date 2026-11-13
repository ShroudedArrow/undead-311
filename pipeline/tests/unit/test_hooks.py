"""Hook scripts decide from the tool name and arguments (the hooks have no matcher).

Sample payloads cover shell tools, file-writing tools and unknown tools for scripts/guard.py and
scripts/kill_switch.py. No network: the kill switch has no token here, so GitHub is "unreachable" (fail-open) and
only the .kiro/STOP file decides.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import guard
import hooklib
import kill_switch


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_CHANNEL_TOKEN", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    (tmp_path / ".kiro").mkdir()
    return tmp_path


def shell(tool: str, command: str) -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}}


def writer(tool: str, path: str, **extra) -> dict:
    return {"tool_name": tool, "tool_input": {"path": path, **extra}}


# ---- classification -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["shell", "execute_bash", "bash", "run_shell_command", "terminal", "executeBash"])
def test_shell_tool_names(name):
    assert hooklib.tool_kind(name) == "shell"


@pytest.mark.parametrize("name", ["fs_write", "fs_append", "str_replace", "delete_file", "write", "createHook",
                                  "mcp__fs__write_file", "apply_patch"])
def test_write_tool_names(name):
    assert hooklib.tool_kind(name) == "write"


@pytest.mark.parametrize("name", ["read_file", "list_directory", "grep_search", "file_search", "web_fetch",
                                  "run_workflow", "send_message", "totally_new_tool", ""])
def test_other_and_unknown_tool_names(name):
    assert hooklib.tool_kind(name) == "other"


# ---- guard: shell tools ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["shell", "execute_bash", "run_shell_command"])
@pytest.mark.parametrize("command", [
    "git push --force origin HEAD:refs/heads/x",
    "git push -f",
    "git push origin +main",
    "git reset --hard HEAD~1",
    "git clean -fd",
])
def test_guard_blocks_forbidden_commands_on_any_shell_tool(root, tool, command):
    assert guard.decide(shell(tool, command), root)


def test_guard_blocks_rm_rf_inside_repo(root):
    (root / "pipeline").mkdir()
    assert guard.decide(shell("execute_bash", f"rm -rf {root}/pipeline"), root)


@pytest.mark.parametrize("command", [
    "echo hi > .kiro/steering/x.md",
    "sed -i 's/a/b/' .kiro/hooks/guard.json",
    "rm .kiro/STOP",
])
def test_guard_blocks_shell_edits_of_protected_paths(root, command, monkeypatch):
    monkeypatch.chdir(root)
    assert guard.decide(shell("execute_bash", command), root)


@pytest.mark.parametrize("command", ["git status", "git push origin HEAD", "ls -la", "make test", "git push --dry-run"])
def test_guard_allows_ordinary_commands(root, command):
    assert guard.decide(shell("execute_bash", command), root) is None


# ---- guard: file-writing tools --------------------------------------------------------------------------------

PROTECTED = [
    ".kiro/steering/zombie-definition.md",
    ".kiro/settings/mcp.json",
    ".kiro/hooks/guard.json",
    ".kiro/agents/engine.json",
    ".kiro/STOP",
    "pipeline/tests/fixtures/expected_zombies.json",
]


@pytest.mark.parametrize("tool", ["fs_write", "fs_append", "str_replace", "delete_file", "write", "mcp__fs__write_file"])
@pytest.mark.parametrize("rel", PROTECTED)
def test_guard_blocks_writes_to_protected_paths(root, tool, rel):
    assert guard.decide(writer(tool, str(root / rel)), root)


@pytest.mark.parametrize("rel", [
    ".kiro/workflow-runs/run-1/report.md",
    "docs/DECISIONS.md",
    "pipeline/undead311/ingest/times.py",
    ".kiro/specs/zombie-engine/design.md",
])
def test_guard_allows_writes_elsewhere(root, rel):
    assert guard.decide(writer("fs_write", str(root / rel)), root) is None


def test_guard_allows_writes_outside_repo(root, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere")
    assert guard.decide(writer("fs_write", str(other / ".kiro" / "steering" / "x.md")), root) is None


# ---- guard: unknown and read-only tools -----------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"tool_name": "read_file", "tool_input": {"path": ".kiro/steering/zombie-definition.md"}},
    {"tool_name": "list_directory", "tool_input": {"path": ".kiro/hooks"}},
    {"tool_name": "grep_search", "tool_input": {"query": "git push --force"}},
    {"tool_name": "totally_new_tool", "tool_input": {"command": "git push --force", "path": ".kiro/STOP"}},
    {"tool_name": "", "tool_input": {"command": "git push --force"}},
    {},
])
def test_guard_allows_unknown_and_read_only_tools(root, payload):
    assert guard.decide(payload, root) is None


def test_guard_accepts_alternate_payload_spellings(root):
    payload = {"toolName": "execute_bash", "toolInput": {"command": "git push --force"}}
    assert guard.decide(payload, root)
    payload = {"toolName": "fs_write", "toolInput": {"targetFile": str(root / ".kiro/hooks/x.json")}}
    assert guard.decide(payload, root)


def test_hook_files_have_no_matcher():
    import json

    hooks = Path(__file__).resolve().parents[3] / ".kiro" / "hooks"
    for fname in ("guard.json", "kill-switch.json"):
        for h in json.loads((hooks / fname).read_text())["hooks"]:
            if h["trigger"] == "PreToolUse":
                assert "matcher" not in h, f"{fname}:{h['name']} must run on every PreToolUse event"


# ---- kill switch ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    shell("execute_bash", "make test"),
    shell("shell", "ls"),
    writer("fs_write", "docs/x.md"),
    writer("str_replace", "docs/x.md"),
    {},                                    # no tool named: a task hook
])
def test_kill_switch_applies_to_shell_write_and_task_events(payload):
    assert kill_switch.applies(payload)


@pytest.mark.parametrize("payload", [
    {"tool_name": "read_file", "tool_input": {"path": "README.md"}},
    {"tool_name": "list_directory", "tool_input": {"path": "."}},
    {"tool_name": "web_fetch", "tool_input": {"url": "https://example.com"}},
    {"tool_name": "totally_new_tool", "tool_input": {}},
])
def test_kill_switch_ignores_reads_and_unknown_tools(payload):
    assert not kill_switch.applies(payload)


def test_kill_switch_halts_when_stop_file_exists(root):
    (root / ".kiro" / "STOP").write_text("stop")
    blocked, why = kill_switch.decide(root)
    assert blocked and "STOP" in why


def test_kill_switch_allows_when_no_signal_and_github_unreachable(root):
    blocked, why = kill_switch.decide(root)
    assert not blocked and "fail-open" in why
