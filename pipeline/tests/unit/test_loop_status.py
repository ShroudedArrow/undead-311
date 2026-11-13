"""scripts/loop_status.py writes a loop's stop file: done is true only for a PASS gate and a later APPROVED review.

No spec requirement covers the workflow recipes; this backs the smoke-2 loop-stop fix (run wf_7e2703967ec25e5b).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "loop_status.py"


def run(tmp_path: Path, gate: dict | None, review: dict | None, review_first: bool = False) -> dict:
    g, r, out = tmp_path / "gate.json", tmp_path / "review.json", tmp_path / "sub" / "loop.json"
    if gate is not None:
        g.write_text(json.dumps(gate))
    if review is not None:
        r.write_text(json.dumps(review))
    if review_first and gate is not None and review is not None:
        os.utime(r, (1_000, 1_000))
        os.utime(g, (2_000, 2_000))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--gate", str(g), "--review", str(r), "--out", str(out)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(out.read_text())


def test_done_only_for_pass_and_approved(tmp_path):
    assert run(tmp_path, {"status": "PASS"}, {"verdict": "APPROVED"})["done"] is True


@pytest.mark.parametrize(("gate", "review"), [
    ({"status": "PASS"}, {"verdict": "CHANGES_REQUESTED"}),
    ({"status": "FAIL"}, {"verdict": "APPROVED"}),
    ({"status": "FAIL"}, {"verdict": "CHANGES_REQUESTED"}),
    (None, {"verdict": "APPROVED"}),
    ({"status": "PASS"}, None),
    (None, None),
])
def test_anything_else_writes_done_false(tmp_path, gate, review):
    out = run(tmp_path, gate, review)
    assert out["done"] is False


def test_an_approval_older_than_the_gate_does_not_stop_the_loop(tmp_path):
    assert run(tmp_path, {"status": "PASS"}, {"verdict": "APPROVED"}, review_first=True)["done"] is False
