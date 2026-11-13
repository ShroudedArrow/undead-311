"""Combine a loop's gate JSON and review JSON into the loop's stop-condition file.

done = gate.status == "PASS" AND review.verdict == "APPROVED" AND the review was written after the gate
(so an approval of an older commit can't end the loop).
Usage: python3 scripts/loop_status.py --gate G.json --review R.json --out L.json
Always exits 0; the workflow reads `$.done` from the output file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(p: str) -> dict:
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True)
    ap.add_argument("--review", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    gate, review = load(a.gate), load(a.review)
    fresh = Path(a.review).exists() and Path(a.gate).exists() and Path(a.review).stat().st_mtime >= Path(a.gate).stat().st_mtime
    done = gate.get("status") == "PASS" and review.get("verdict") == "APPROVED" and fresh
    out = {"done": done, "gate": gate.get("status"), "verdict": review.get("verdict"), "review_after_gate": fresh}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out) + "\n")
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
