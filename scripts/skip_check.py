#!/usr/bin/env python3
"""Decide whether a recipe step runs or is skipped because of the `start_at` launch input.

The build recipe has no conditional nodes, and a repeat always runs its body once, so a relaunch cannot leave earlier loops
out of the tree. Instead every step calls this script first (docs/RUN_PROTOCOL.md, step 1b). A node is skipped when it comes
before `start_at` in the recipe's document order. Parent containers of `start_at` and the `setup` step are never skipped.

Usage:
  skip_check.py --step-id ID --run-id RUN [--start-at ID] [--recipe FILE] [--runs-dir DIR]   exit 0 = run, exit 3 = skip
      (start_at comes from .kiro/workflow-runs/<run_id>/start_at.json unless given)
  skip_check.py --start-at ID --validate                                                  exit 0 = start_at names a node
`--start-at` may be empty, or the literal text `{{start_at}}` when the launcher passed nothing: nothing is skipped.
When a skipped step is the last step of a repeat (the review step), the script also writes the repeat's stop file
`{"done": true, "skipped": true}` so the loop ends after one empty pass. Needs PyYAML (a project dependency).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # system python3 has no PyYAML: re-run inside the project environment once
    import os

    if os.environ.get("SKIP_CHECK_REEXEC"):
        raise
    os.environ["SKIP_CHECK_REEXEC"] = "1"
    os.chdir(Path(__file__).resolve().parents[1])
    os.execvp("uv", ["uv", "run", "--frozen", "python", str(Path(__file__).resolve()), *sys.argv[1:]])

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECIPE = ROOT / ".kiro" / "workflows" / "build-undead-311.workflow.yaml"
SKIP_EXIT = 3
ALWAYS_RUN = {"setup"}


def normalize(start_at: str | None) -> str:
    """Empty or unresolved launch input means: start from the beginning."""
    s = (start_at or "").strip()
    return "" if s.startswith("{{") else s


def walk(node: dict, parents: tuple[str, ...], out: list[dict]) -> None:
    out.append({"id": node["id"], "parents": parents, "node": node})
    children = [*node.get("steps", []), *node.get("branches", [])]
    for child in children:
        walk(child, parents + (node["id"],), out)


def flatten(recipe: dict) -> list[dict]:
    """Every node in document order with the ids of its ancestors."""
    out: list[dict] = []
    for node in recipe["steps"]:
        walk(node, (), out)
    return out


def load(path: Path) -> list[dict]:
    return flatten(yaml.safe_load(path.read_text(encoding="utf-8")))


def skipped(flat: list[dict], start_at: str, step_id: str) -> bool:
    """True when `step_id` precedes `start_at` in document order and does not contain it."""
    start_at = normalize(start_at)
    if not start_at or step_id in ALWAYS_RUN:
        return False
    ids = [n["id"] for n in flat]
    if start_at not in ids:
        raise ValueError(f"start_at {start_at!r} is not a node id in the recipe")
    if step_id not in ids:
        raise ValueError(f"step {step_id!r} is not a node id in the recipe")
    start = flat[ids.index(start_at)]
    return ids.index(step_id) < ids.index(start_at) and step_id not in start["parents"]


def stop_file_for(flat: list[dict], step_id: str, run_id: str) -> Path | None:
    """The stop file of the repeat whose last child is `step_id`, with {{run_id}} filled in."""
    for n in flat:
        node = n["node"]
        if node.get("type") == "repeat" and node["steps"] and node["steps"][-1]["id"] == step_id:
            raw = node.get("stopCondition", {}).get("fileCheck", {}).get("path")
            return Path(raw.replace("{{run_id}}", run_id)) if raw else None
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    ap.add_argument(
        "--start-at",
        default=None,
        help="default: read from <runs dir>/<run id>/start_at.json, written by setup",
    )
    ap.add_argument("--step-id")
    ap.add_argument("--run-id")
    ap.add_argument(
        "--runs-dir",
        type=Path,
        help="the workflow-runs folder (default .kiro/workflow-runs in this checkout); tests point it at a temp folder",
    )
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args(argv)
    flat = load(a.recipe)
    start_at = a.start_at
    if start_at is None and a.run_id:
        f = (a.runs_dir or ROOT / ".kiro" / "workflow-runs") / a.run_id / "start_at.json"
        start_at = json.loads(f.read_text()).get("start_at", "") if f.exists() else ""
    start_at = normalize(start_at)
    if a.validate:
        if start_at and start_at not in {n["id"] for n in flat}:
            print(f"start_at {start_at!r} is not a node id in {a.recipe.name}", file=sys.stderr)
            return 2
        print("start_at ok:", start_at or "(from the beginning)")
        return 0
    if not a.step_id or not a.run_id:
        ap.error("--step-id and --run-id are required unless --validate")
    try:
        skip = skipped(flat, start_at, a.step_id)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not skip:
        print(f"run {a.step_id}")
        return 0
    stop = stop_file_for(flat, a.step_id, a.run_id)
    if stop is not None:
        if a.runs_dir:
            stop = a.runs_dir / a.run_id / stop.name
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.write_text(
            json.dumps({"done": True, "skipped": True, "reason": f"before start_at {start_at}"}) + "\n"
        )
    print(f"skip {a.step_id}: before start_at {start_at}")
    return SKIP_EXIT


if __name__ == "__main__":
    sys.exit(main())
