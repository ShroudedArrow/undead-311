"""`make snapshot`: freeze the judging snapshot into data/SNAPSHOT.md (REQ-OPS-SNAP.1).

  python pipeline/scripts/snapshot.py                    write the judging section
  python pipeline/scripts/snapshot.py --check            exit 1 when the files no longer match the section
  options: --data-end YYYY-MM-DD  --tag NAME  --public DIR  --processed DIR  --snapshot FILE

Paths default to the checkout this script lives in (so a git worktree writes its own SNAPSHOT.md) and to
$DATA_DIR/processed with the tech.md fallback. Logic and format: pipeline/undead311/snapshot.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from undead311 import snapshot as snap
from undead311.paths import data_dir

CHECKOUT = HERE.parents[1]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="compare the files with the committed section; change nothing")
    p.add_argument("--data-end", default=None, help="date the data runs through (default: data_end in status.json)")
    p.add_argument("--tag", default=None, help="git tag name to record (default: judged-<data end>)")
    p.add_argument("--public", type=Path, default=CHECKOUT / "web" / "public" / "data")
    p.add_argument("--processed", type=Path, default=None, help="default: $DATA_DIR/processed")
    p.add_argument("--snapshot", type=Path, default=CHECKOUT / "data" / "SNAPSHOT.md")
    args = p.parse_args(argv)

    processed = args.processed if args.processed is not None else data_dir() / "processed"
    section = snap.build(args.public, processed, args.data_end, args.tag)
    current = args.snapshot.read_text() if args.snapshot.exists() else ""
    if args.check:
        same = snap.extract_section(current) == section
        print("snapshot: files match the judging section" if same else "snapshot: files differ from the judging section (or it is missing)")
        return 0 if same else 1
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    args.snapshot.write_text(snap.upsert_section(current, section))
    tag = args.tag or snap.default_tag(args.data_end or snap.data_end_of(args.public))
    print(f"snapshot: wrote the judging section of {args.snapshot}")
    print(f"snapshot: next, the owner tags the release: git tag -a {tag} -m 'Judging snapshot' && git push origin {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
