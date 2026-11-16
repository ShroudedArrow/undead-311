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
RUN_CREATED = {"docs/METHODS.md", "docs/VALIDATION.md", "docs/DEPLOY.md"}
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
    expected = {"run_id", "base_branch", "start_at", "carry_from"} if data["name"] == "build-undead-311" else {"run_id"}
    assert set(data["inputs"]) == expected
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


# ---- repeat loops: each stop file is written inside its own loop ---------------------------------------------
# No spec requirement covers the workflow recipes; these tests cite the smoke-2 finding (run wf_7e2703967ec25e5b):
# the engine warned that no step inside `hello-loop` wrote its stop file, because the prompts named it by a relative
# path while the stopCondition uses the absolute one, so a loop could never stop on its own.

LOOP_CALL = re.compile(
    rf"python3 {ABS_REPO}/scripts/loop_status\.py --gate (\S+) --review (\S+) --out (\S+?)`"
)
GATE_CALL = re.compile(r"validate_gate\.py .*?--out (\S+)")
REVIEW_WRITE = re.compile(r"Write (\.kiro/workflow-runs/\{\{run_id\}\}/\S+\.json)")


def repeats_of(recipe: Path):
    return [n for n in walk(yaml.safe_load(recipe.read_text())) if n.get("type") == "repeat"]


def run_file(path: str) -> str:
    """The absolute main-checkout path of a run file named either way."""
    return path if path.startswith("/") else f"{ABS_REPO}/{path}"


def fs_write_allows(agent: str, rel: str) -> bool:
    from fnmatch import fnmatch

    rules = json.loads((REPO / ".kiro" / "agents" / f"{agent}.json").read_text())["permissions"]["rules"]
    allowed = denied = False
    for rule in rules:
        if rule["capability"] != "fs_write":
            continue
        hit = any(fnmatch(p, m) for m in rule["match"] for p in (rel, run_file(rel)))
        if hit and not any(fnmatch(p, x) for x in rule.get("exclude", []) for p in (rel, run_file(rel))):
            allowed |= rule["effect"] == "allow"
            denied |= rule["effect"] == "deny"
    return allowed and not denied


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda p: p.name)
def test_every_repeat_stop_file_is_written_by_its_own_review_step(recipe):
    """smoke-2 finding: each repeat's stop file is the --out of loop_status.py in that loop's last (review) step."""
    repeats = repeats_of(recipe)
    assert repeats, f"{recipe.name} has no repeat node"
    all_steps = steps_of(recipe)
    for r in repeats:
        check = r["stopCondition"]["fileCheck"]
        stop = check["path"]
        assert (check["jsonPath"], check["value"]) == ("$.done", True), r["id"]
        inner = [s for s in walk(r["steps"]) if s.get("type") == "step"]
        if stop.endswith("/{{run_id}}.done.json"):
            # fix/fulldata-2: a leg loop. `run_full.py` itself writes `<run_id>.done.json` after every leg (done true only when
            # the pipeline finished), so there is no review step; the leg step must pass that exact path to the script.
            legs = [s for s in inner if "run_full.py" in s["prompt"] and f"--done-file {stop}" in s["prompt"]]
            assert len(legs) == 1 and legs[0] is inner[-1], f"{r['id']}: the leg step must run run_full.py with --done-file {stop}"
            assert "--budget-min" in legs[0]["prompt"], f"{r['id']}: a leg needs a time budget"
            continue
        writers = [s for s in inner if any(m[2] == stop for m in LOOP_CALL.findall(s["prompt"]))]
        assert len(writers) == 1, f"{r['id']}: {len(writers)} steps inside the loop write {stop}"
        writer = writers[0]
        assert writer is inner[-1], f"{r['id']}: the stop file must be written by the loop's last step"
        assert writer["agent"].startswith("reviewer-"), f"{r['id']}: the review step writes the stop file"
        assert writer["prompt"].count(stop) >= 2, f"{r['id']}: the prompt names the stop file by its absolute path"
        # its inputs: a gate written earlier in the same loop, and the review file this step writes
        gate, review, _ = next(m for m in LOOP_CALL.findall(writer["prompt"]) if m[2] == stop)
        assert gate.startswith("/") and review.startswith("/"), f"{r['id']}: loop_status.py paths must be absolute"
        gates = {run_file(g) for s in inner[:-1] for g in GATE_CALL.findall(s["prompt"])}
        assert gate in gates, f"{r['id']}: gate {gate} is not written by an earlier step of the loop"
        writes = {run_file(w) for w in REVIEW_WRITE.findall(writer["prompt"])}
        assert review in writes, f"{r['id']}: review file {review} is not the one the review step writes"
        # the reviewer agent is allowed to write that review file
        rel = review[len(ABS_REPO) + 1:].replace("{{run_id}}", "run-x")
        assert fs_write_allows(writer["agent"], rel), f"{r['id']}: {writer['agent']} may not write {rel}"
        # nothing outside the loop names the stop file
        inner_ids = {s["id"] for s in inner}
        for s in all_steps:
            if s["id"] not in inner_ids:
                assert stop not in s["prompt"] and stop.split("/")[-1] not in s["prompt"], (
                    f"step {s['id']} outside {r['id']} names its stop file"
                )


def test_stop_file_check_catches_a_loop_without_a_writer(tmp_path):
    """smoke-2 finding: the check fails on the pre-fix shape (relative --out, absolute stopCondition)."""
    bad = tmp_path / "bad.workflow.yaml"
    bad.write_text(yaml.safe_dump({"steps": [{
        "type": "repeat", "id": "l",
        "stopCondition": {"fileCheck": {"path": f"{ABS_REPO}/.kiro/workflow-runs/{{{{run_id}}}}/l.json",
                                        "jsonPath": "$.done", "value": True}},
        "steps": [{"type": "step", "id": "review", "agent": "reviewer-stats", "prompt":
                   f"`python3 {ABS_REPO}/scripts/loop_status.py --gate .kiro/workflow-runs/{{{{run_id}}}}/g.json "
                   f"--review .kiro/workflow-runs/{{{{run_id}}}}/review-stats.json --out .kiro/workflow-runs/{{{{run_id}}}}/l.json`"}],
    }]}))
    with pytest.raises(AssertionError, match="0 steps inside the loop"):
        test_every_repeat_stop_file_is_written_by_its_own_review_step(bad)
