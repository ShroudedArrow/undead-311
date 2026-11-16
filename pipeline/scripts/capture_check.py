"""Gate for `make capture` (REQ-OPS-CAPTURE.1, REQ-OPS-SNAP.2): capture only from the frozen judging snapshot.

    python pipeline/scripts/capture_check.py [--served web/dist/data] [--snapshot data/SNAPSHOT.md] [--dev]

Exits 1 when the served data does not match the judging section of data/SNAPSHOT.md. With --dev (make capture
CAPTURE_DEV=1) it continues and writes docs/media/NOT-SNAPSHOT.txt instead.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from undead311 import capture_guard

CHECKOUT = HERE.parents[1]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--served", type=Path, default=CHECKOUT / "web" / "dist" / "data")
    p.add_argument("--snapshot", type=Path, default=CHECKOUT / "data" / "SNAPSHOT.md")
    p.add_argument("--media", type=Path, default=CHECKOUT / "docs" / "media")
    p.add_argument("--dev", action="store_true", help="capture anyway and write a NOT-SNAPSHOT marker into docs/media/")
    args = p.parse_args(argv)
    text = args.snapshot.read_text(encoding="utf-8") if args.snapshot.exists() else ""
    problems = capture_guard.check(args.served, text)
    code = capture_guard.apply_marker(args.media, problems, args.dev)
    for line in problems[:20]:
        print(f"capture: {line}", file=sys.stderr)
    if len(problems) > 20:
        print(f"capture: ... and {len(problems) - 20} more", file=sys.stderr)
    if not problems:
        print("capture: the served data is the judging snapshot")
    elif code == 0:
        print("capture: NOT the judging snapshot; continuing because --dev was given (NOT-SNAPSHOT marker written)", file=sys.stderr)
    else:
        print("capture: the served data does not match data/SNAPSHOT.md; refusing (use CAPTURE_DEV=1 for a development run)", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
