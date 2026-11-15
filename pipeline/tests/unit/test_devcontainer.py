"""Check O5 (nightly-and-deploy design): the Codespaces dev container is valid and uses the repo's pinned versions.

REQ-OPS-DEV.1: Python 3.11, uv, and Node from `.nvmrc`, with `make setup && make pipeline-sample && make web` working.
REQ-OPS-DEV.2: `DATA_DIR` is the gitignored `.local-data/data`, and the dev-server port is forwarded.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FILE = REPO / ".devcontainer" / "devcontainer.json"


@pytest.fixture(scope="module")
def cfg() -> dict:
    return json.loads(FILE.read_text())          # plain JSON (no comments), so any tool can read it


def test_python_version_matches_dot_python_version(cfg):
    """REQ-OPS-DEV.1 (check O5): the image's Python is the one in .python-version."""
    wanted = (REPO / ".python-version").read_text().strip()
    assert re.search(rf"python:[\w.-]*{re.escape(wanted)}\b", cfg["image"]), (cfg["image"], wanted)
    assert re.search(r"^mcr\.microsoft\.com/devcontainers/python:", cfg["image"])


def test_node_version_matches_nvmrc(cfg):
    """REQ-OPS-DEV.1 (check O5): the Node feature runs the major version in .nvmrc."""
    wanted = (REPO / ".nvmrc").read_text().strip().lstrip("v").split(".")[0]
    node = cfg["features"]["ghcr.io/devcontainers/features/node:1"]
    assert str(node["version"]).split(".")[0] == wanted


def test_uv_is_pinned_and_make_setup_runs_after_it(cfg):
    """REQ-OPS-DEV.1: an exact uv version, installed before `make setup`."""
    cmd = cfg["postCreateCommand"]
    assert re.search(r"uv==\d+\.\d+\.\d+", cmd) and cmd.index("uv==") < cmd.index("make setup")


def test_data_dir_is_the_gitignored_local_data_folder_and_exists_before_setup(cfg):
    """REQ-OPS-DEV.2: DATA_DIR under .local-data (gitignored), created first so the Makefile uses it instead of its fallback."""
    assert cfg["containerEnv"]["DATA_DIR"] == "${containerWorkspaceFolder}/.local-data/data"
    assert ".local-data/data" in cfg["onCreateCommand"]
    assert ".local-data/" in (REPO / ".gitignore").read_text().splitlines()


def test_the_dev_server_port_is_forwarded(cfg):
    """REQ-OPS-DEV.2: `make web` runs vite, whose default port is 5173; it is forwarded and labeled."""
    assert 5173 in cfg["forwardPorts"] and "5173" in cfg["portsAttributes"]
    assert "--port" not in (REPO / "web" / "package.json").read_text().split('"dev"')[1].split(",")[0]
    assert not re.search(r"\bport\s*:", (REPO / "web" / "vite.config.ts").read_text())   # no custom dev port


def test_the_commands_the_container_promises_exist_in_the_makefile():
    """REQ-OPS-DEV.1: `make setup`, `make pipeline-sample` and `make web` are real targets."""
    targets = set(re.findall(r"^([a-z][\w-]*):", (REPO / "Makefile").read_text(), re.MULTILINE))
    assert {"setup", "pipeline-sample", "web"} <= targets


def test_no_secret_or_third_party_script_in_the_container_file(cfg):
    """REQ-OPS-DEV.1: nothing secret, and only reviewed VS Code extensions."""
    text = FILE.read_text()
    assert not re.search(r"(?i)(token|secret|password)", text)
    assert set(cfg["customizations"]["vscode"]["extensions"]) <= {"ms-python.python", "charliermarsh.ruff"}
