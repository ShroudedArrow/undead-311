"""Workflow validate gate: run `make test` and `make lint` and write PASS/FAIL to a JSON file.

Deterministic on purpose: the gate is a script, not an agent's opinion (testing.md: agents don't grade their own work).
Usage: python3 scripts/validate_gate.py --out .kiro/workflow-runs/<run_id>/<name>-gate.json [--cwd <worktree>]
       [--target test --target lint]   (defaults: test, lint)
Exit code mirrors the result (0 PASS, 1 FAIL) but the JSON file is the workflow's source of truth.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

TAIL = 40


def run(target: str, cwd: Path) -> dict:
    p = subprocess.run(["make", target], cwd=cwd, capture_output=True, text=True, timeout=1500, check=False)
    tail = (p.stdout + p.stderr).strip().splitlines()[-TAIL:]
    return {"target": target, "exit_code": p.returncode, "ok": p.returncode == 0, "tail": tail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--target", action="append")
    a = ap.parse_args()
    cwd = Path(a.cwd).resolve()
    results = [run(t, cwd) for t in (a.target or ["test", "lint"])]
    status = "PASS" if all(r["ok"] for r in results) else "FAIL"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False).stdout.strip()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"status": status, "commit": head, "cwd": str(cwd),
                               "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "results": results}, indent=2) + "\n")
    print(f"gate {status} -> {out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
