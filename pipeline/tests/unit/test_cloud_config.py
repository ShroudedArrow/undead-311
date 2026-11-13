"""The agents, steering and workflows load from Kiro Web's cloud configuration (/projects/sandbox/.kiro), not from the repo.

These tests copy hooks/, agents/, steering/ and workflows/ into a stand-in cloud folder and check that every reference
still resolves from there: absolute /projects/sandbox/undead-311/... paths (mapped to this checkout, so the tests run
anywhere), ../steering references between cloud folders, and the recipes' scripts, docs, Makefile targets and agents.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
ABS_REPO = "/projects/sandbox/undead-311"
ABS_WORKTREES = "/projects/sandbox/worktrees"
CLOUD_DIRS = ("hooks", "agents", "steering", "workflows")
# files a run creates or a spec adds later; they are not expected to exist in the repo yet
RUN_CREATED = {"docs/METHODS.md", "docs/VALIDATION.md"}
RUN_CREATED_TARGETS = {"hello"}                      # the smoke recipe adds this Makefile target itself


@pytest.fixture(scope="module")
def cloud(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp("sandbox") / ".kiro"
    for d in CLOUD_DIRS:
        shutil.copytree(REPO / ".kiro" / d, dest / d)
    return dest


def local(path: str) -> Path:
    """Map an absolute repo path to this checkout."""
    assert path.startswith(ABS_REPO + "/"), path
    return REPO / path[len(ABS_REPO) + 1:]


AGENTS = sorted((REPO / ".kiro" / "agents").glob("*.json"))
RECIPES = sorted((REPO / ".kiro" / "workflows").glob("*.yaml"))
STEERING = sorted((REPO / ".kiro" / "steering").glob("*.md"))


# ---- agents ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_agent_resources_resolve_from_cloud_folder(agent, cloud):
    for res in json.loads(agent.read_text())["resources"]:
        assert res.startswith("file://")
        target = res[len("file://"):]
        if target.startswith("/"):
            assert target.startswith(ABS_REPO + "/"), f"{res}: absolute paths must be under {ABS_REPO}"
            assert local(target).is_file(), res
        else:
            assert (cloud / "agents" / target).resolve().is_file(), f"{res} does not resolve from the cloud folder"


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_agent_prompts_and_permissions_use_absolute_script_paths(agent):
    d = json.loads(agent.read_text())
    assert "python3 scripts/" not in d["prompt"]
    # documents the agent reads are absolute; file-ownership lists (docs/KIRO_LOG.md, ...) stay repo-relative
    assert not re.search(r"(Follow|Read) docs/", d["prompt"])
    for m in re.findall(rf"{ABS_REPO}/([\w./-]+?\.(?:md|py))", d["prompt"]):
        assert (REPO / m).is_file(), m
    for rule in d["permissions"]["rules"]:
        if rule["capability"] == "shell" and rule["effect"] == "allow" and "python3 scripts/*" in rule["match"]:
            assert f"python3 {ABS_REPO}/scripts/*" in rule["match"]
            assert f"cd {ABS_REPO}*" in rule["match"]
        if rule["capability"] == "fs_write" and rule["effect"] == "allow":
            for m in rule["match"]:
                if not m.startswith(("*", "/")):
                    assert f"{ABS_REPO}/{m}" in rule["match"] and f"{ABS_WORKTREES}/*/{m}" in rule["match"]


# ---- steering -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("steer", STEERING, ids=lambda p: p.stem)
def test_steering_references_resolve(steer):
    text = steer.read_text()
    for ref in re.findall(r"#\[\[file:([^\]]+)\]\]", text):
        assert ref.startswith(ABS_REPO + "/"), f"{steer.name}: {ref} must be an absolute path under {ABS_REPO}"
        assert local(ref).is_file(), ref
    m = re.search(r"^fileMatchPattern: (\[.*\])$", text, re.MULTILINE)
    if m:
        for pat in json.loads(m.group(1)):
            assert pat.startswith("**/"), f"{steer.name}: {pat} must match under any workspace prefix"


# ---- workflows ------------------------------------------------------------------------------------------------

def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def steps_of(recipe: Path):
    return [n for n in walk(yaml.safe_load(recipe.read_text())) if n.get("type") == "step"]


MAKEFILE_TARGETS = set(re.findall(r"^([\w-]+):", (REPO / "Makefile").read_text(), re.MULTILINE))


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_every_step_starts_in_the_repo_folder(recipe):
    steps = steps_of(recipe)
    assert steps
    for s in steps:
        first = s["prompt"].lstrip().splitlines()[0]
        assert f"`cd {ABS_REPO}`" in first, f"step {s['id']} does not start with cd {ABS_REPO}"


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_recipe_inputs_and_worktrees(recipe):
    data = yaml.safe_load(recipe.read_text())
    assert set(data["inputs"]) == {"run_id"}
    text = recipe.read_text()
    assert "worktree_path" not in text
    assert ".local-data/worktrees" not in text
    for path in re.findall(r"git worktree add -b \S+ (\S+)", text):
        assert path.startswith(f"{ABS_WORKTREES}/{{{{run_id}}}}"), path


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_recipe_paths_resolve(recipe):
    text = recipe.read_text()
    data = yaml.safe_load(text)
    # stop-condition files live in the main checkout, by absolute path
    for n in walk(data):
        if "fileCheck" in n:
            assert n["fileCheck"]["path"].startswith(f"{ABS_REPO}/.kiro/workflow-runs/{{{{run_id}}}}/")
    # scripts are run by absolute path and exist
    assert not re.search(r"python3 scripts/", text)
    for script in re.findall(rf"python3 {ABS_REPO}/(scripts/\w+\.py)", text):
        assert (REPO / script).is_file(), script
    # repo documents named in prompts exist
    for doc in set(re.findall(r"(?<![\w/.-])(docs/[A-Z_]+\.md)", text)) - RUN_CREATED:
        assert (REPO / doc).is_file(), doc
    # gate targets exist in the Makefile
    for target in set(re.findall(r"--target ([\w-]+)", text)) - RUN_CREATED_TARGETS:
        assert target in MAKEFILE_TARGETS, target
    # every agent exists (repo agent file) or is a built-in workflow agent
    for n in walk(data):
        if "agent" in n and not n["agent"].startswith("wf-"):
            assert (REPO / ".kiro" / "agents" / f"{n['agent']}.json").is_file(), n["agent"]


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_file_ownership_lists_stay_repo_relative(recipe):
    for block in re.findall(r'"ownership": \{.*?\}\}', recipe.read_text(), re.DOTALL):
        for item in re.findall(r'"([^"]+)"', block)[1:]:
            assert not item.startswith("/") and "projects" not in item, item
