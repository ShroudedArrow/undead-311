"""start_at skipping for the build recipe (scripts/skip_check.py; run protocol step 1b) and its launch inputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import skip_check

RECIPE = REPO / ".kiro" / "workflows" / "build-undead-311.workflow.yaml"


@pytest.fixture(scope="module")
def flat():
    return skip_check.load(RECIPE)


def test_recipe_declares_base_branch_and_start_at():
    inputs = yaml.safe_load(RECIPE.read_text())["inputs"]
    assert {"run_id", "base_branch", "start_at"} <= set(inputs)
    assert "default main" in inputs["base_branch"]


def test_durability_stats_credibility_loop_has_five_iterations(flat):
    node = next(n["node"] for n in flat if n["id"] == "durability-stats-credibility-loop")
    assert node["maxIterations"] == 5


def test_every_other_loop_keeps_three(flat):
    others = {
        n["id"]: n["node"]["maxIterations"]
        for n in flat
        if n["node"].get("type") == "repeat" and n["id"] != "durability-stats-credibility-loop"
    }
    assert others and set(others.values()) == {3}


def test_no_start_at_skips_nothing(flat):
    for start in ("", None, "{{start_at}}"):
        assert not any(skip_check.skipped(flat, start, n["id"]) for n in flat)


def test_start_at_skips_earlier_nodes_only(flat):
    start = "durability-stats-credibility-loop"
    assert skip_check.skipped(flat, start, "zombie-engine-demo-critical-implement")
    assert skip_check.skipped(flat, start, "integrate-demo-critical")
    assert skip_check.skipped(flat, start, "zombie-engine-credibility-review")
    for later in (
        "durability-stats-credibility-implement",
        "durability-stats-credibility-review",
        "nightly-and-deploy-credibility-loop",
        "haunted-web-credibility-implement",
        "integrate-credibility",
        "design-gate",
    ):
        assert not skip_check.skipped(flat, start, later), later


def test_setup_and_parents_of_start_at_are_never_skipped(flat):
    start = "durability-stats-credibility-review"
    assert not skip_check.skipped(flat, start, "setup")
    assert not skip_check.skipped(flat, start, "durability-stats-credibility-loop")  # parent repeat
    assert not skip_check.skipped(flat, start, "credibility-parallel")  # grandparent
    assert skip_check.skipped(flat, start, "durability-stats-credibility-implement")  # earlier sibling


def test_unknown_ids_are_errors(flat):
    with pytest.raises(ValueError):
        skip_check.skipped(flat, "no-such-loop", "setup-x")
    with pytest.raises(ValueError):
        skip_check.skipped(flat, "durability-stats-credibility-loop", "no-such-step")


def test_skipped_review_step_writes_the_loop_stop_file(tmp_path):
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "skip_check.py"),
        "--runs-dir",
        str(tmp_path),
        "--run-id",
        "r1",
        "--start-at",
        "durability-stats-credibility-loop",
    ]
    review = subprocess.run(
        [*cmd, "--step-id", "zombie-engine-credibility-review"], capture_output=True, text=True, check=False
    )
    assert review.returncode == skip_check.SKIP_EXIT
    stop = json.loads((tmp_path / "r1" / "zombie-engine-credibility-loop.json").read_text())
    assert stop["done"] is True and stop["skipped"] is True
    implement = subprocess.run(
        [*cmd, "--step-id", "zombie-engine-credibility-implement"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert implement.returncode == skip_check.SKIP_EXIT
    assert len(list((tmp_path / "r1").iterdir())) == 1  # only the review step writes a stop file


def test_start_at_is_read_from_the_run_folder(tmp_path):
    (tmp_path / "r2").mkdir()
    (tmp_path / "r2" / "start_at.json").write_text(json.dumps({"start_at": "integrate-credibility"}))
    base = [
        sys.executable,
        str(REPO / "scripts" / "skip_check.py"),
        "--runs-dir",
        str(tmp_path),
        "--run-id",
        "r2",
    ]
    assert (
        subprocess.run([*base, "--step-id", "coroner-label"], check=False).returncode == skip_check.SKIP_EXIT
    )
    assert subprocess.run([*base, "--step-id", "design-gate"], check=False).returncode == 0
