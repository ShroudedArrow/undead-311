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


def test_guard_allows_unrelated_paths_outside_repo(root, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere")
    assert guard.decide(writer("fs_write", str(other / "notes" / "x.md")), root) is None


# ---- guard: protected paths under any prefix ------------------------------------------------------------------

PREFIXES = ["", "/projects/sandbox/undead-311/", "/projects/sandbox/", "/somewhere/else/", "./", "a/b/../"]


@pytest.mark.parametrize("tool", ["fs_write", "str_replace", "delete_file"])
@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("rel", PROTECTED)
def test_guard_blocks_protected_paths_under_any_prefix(root, tool, prefix, rel):
    assert guard.decide(writer(tool, prefix + rel), root)


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("command", [
    "echo x > {p}.kiro/steering/x.md",
    "rm {p}.kiro/STOP",
    "sed -i s/a/b/ {p}.kiro/hooks/guard.json",
    "git checkout -- {p}.kiro/agents/engine.json",
    "tee {p}pipeline/tests/fixtures/expected_zombies.json",
])
def test_guard_blocks_shell_edits_under_any_prefix(root, prefix, command):
    assert guard.decide(shell("execute_bash", command.format(p=prefix)), root)


@pytest.mark.parametrize("path", [
    "/projects/sandbox/.kiro/workflow-runs/run-1/report.md",
    "/projects/sandbox/undead-311/.kiro/workflow-runs/run-1/report.md",
    ".kiro/workflow-runs/run-1/report.md",
    "/projects/sandbox/.kiro/specs/zombie-engine/design.md",
    "/projects/sandbox/undead-311/docs/DECISIONS.md",
    "/projects/sandbox/.kiro/steeringx/notes.md",
    "/projects/sandbox/pipeline/tests/fixtures/test_town.csv",
])
def test_guard_still_allows_ordinary_paths_under_any_prefix(root, path):
    assert guard.decide(writer("fs_write", path), root) is None


def test_guard_blocks_dotdot_escape_into_protected_path(root):
    assert guard.decide(writer("fs_write", "/projects/sandbox/.kiro/workflow-runs/../hooks/x.json"), root)


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


# ---- hook commands: absolute paths, run from the repo folder, allow when the script is missing -----------------

import json
import subprocess

REPO = Path(__file__).resolve().parents[3]
ABS_REPO = "/projects/sandbox/undead-311"
HOOKS_DIR = REPO / ".kiro" / "hooks"


def _hook_commands():
    for f in sorted(HOOKS_DIR.glob("*.json")):
        for h in json.loads(f.read_text())["hooks"]:
            cmd = h["action"].get("command")
            if cmd:
                yield pytest.param(f.name, h["name"], cmd, id=f"{f.stem}:{h['name']}")


@pytest.mark.parametrize("fname,name,cmd", list(_hook_commands()))
def test_hook_command_uses_absolute_path_not_git_toplevel(fname, name, cmd):
    assert "git rev-parse" not in cmd
    assert f"{ABS_REPO}/" in cmd
    assert f"cd {ABS_REPO}" in cmd or f"make -C {ABS_REPO}" in cmd
    import re
    for script in re.findall(r"scripts/(\w+\.py)", cmd):
        assert (REPO / "scripts" / script).is_file(), f"{fname}: {script} does not exist"


HOOK_CMDS = list(_hook_commands())


def run_hook(cmd: str, payload: dict, cwd: str):
    return subprocess.run(["sh", "-c", cmd], input=json.dumps(payload), capture_output=True, text=True, cwd=cwd, timeout=30, check=False)


def _script_hook_commands():
    for p in HOOK_CMDS:
        if "python3" in p.values[2]:
            yield p


SCRIPT_HOOK_CMDS = list(_script_hook_commands())


@pytest.mark.parametrize("fname,name,cmd", SCRIPT_HOOK_CMDS)
def test_hook_allows_when_script_is_missing(tmp_path, fname, name, cmd):
    missing = cmd.replace(ABS_REPO, str(tmp_path / "no-such-repo"))
    r = run_hook(missing, shell("execute_bash", "git push --force"), cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr


def test_guard_hook_runs_from_sandbox_cwd_and_blocks(tmp_path):
    cmd = json.loads((HOOKS_DIR / "guard.json").read_text())["hooks"][0]["action"]["command"]
    cmd = cmd.replace(ABS_REPO, str(REPO))     # run against this checkout wherever it lives, never skip
    for payload in (shell("execute_bash", "git push --force"),
                    writer("fs_write", "/projects/sandbox/.kiro/hooks/x.json"),
                    writer("fs_write", ".kiro/steering/x.md")):
        r = run_hook(cmd, payload, cwd=str(tmp_path))      # cwd is not a git repo, like /projects/sandbox
        assert r.returncode == 2, (payload, r.stderr)
        assert "GUARD BLOCKED" in r.stderr
    assert run_hook(cmd, shell("execute_bash", "ls"), cwd=str(tmp_path)).returncode == 0
