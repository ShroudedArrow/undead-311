"""`make snapshot`: freeze the judging snapshot into data/SNAPSHOT.md (REQ-OPS-SNAP.1).

  python pipeline/scripts/snapshot.py --run-id R         write the judging section from the exports of run R
                                                         ($DATA_DIR/exports/R; nothing is copied into web/public/data) and copy the
                                                         judge-mode files into data/judging/ (REQ-OPS-SNAP.3)
  python pipeline/scripts/snapshot.py --run-id R --check exit 1 when the files no longer match the section
  python pipeline/scripts/snapshot.py --verify           plain checkout, no data: exit 1 unless the table is self-consistent and
                                                         data/judging/ holds exactly the judge-mode files it lists
  python pipeline/scripts/snapshot.py --freeze-judge     copy the judge-mode files (data/judging/ when it has files, else
                                                         <public>) into <public>/frozen/ (nightly, BEFORE the pipeline runs);
                                                         exit 1 unless each matches the committed section
  python pipeline/scripts/snapshot.py --check-frozen     exit 1 unless <public>/frozen/ equals the committed section
                                                         (nightly, on web/dist/data, BEFORE the deploy)
  options: --data-end YYYY-MM-DD  --tag NAME  --public DIR  --processed DIR  --raw DIR  --snapshot FILE  --judging DIR
           --stage provisional|final (default: provisional)

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
    p.add_argument("--freeze-judge", action="store_true", help="copy the judge-mode files to <public>/frozen/ (REQ-OPS-SNAP.2)")
    p.add_argument("--check-frozen", action="store_true", help="verify <public>/frozen/ against the committed section")
    p.add_argument("--data-end", default=None, help="date the data runs through; must equal data_end in status.json (default: that value)")
    p.add_argument("--tag", default=None, help="git tag name to record (default: judged-<data end>)")
    p.add_argument("--run-id", default=None, help="the run whose exports are snapshotted: reads $DATA_DIR/exports/<run-id> (REQ-OPS-SNAP.3)")
    p.add_argument("--verify", action="store_true", help="plain-checkout check of the committed section and data/judging/ (no data needed)")
    p.add_argument("--judging", type=Path, default=None, help="folder of the committed judge-mode files (default: judging/ beside --snapshot)")
    p.add_argument("--stage", choices=sorted(snap.STAGES), default=None, help="is the judge tour provisional (default) or final")
    p.add_argument("--public", type=Path, default=None, help="served data folder (default: the run's exports with --run-id, else web/public/data)")
    p.add_argument("--processed", type=Path, default=None, help="default: $DATA_DIR/processed")
    p.add_argument("--raw", type=Path, default=None, help="raw input files; default: the `raw` folder beside --processed")
    p.add_argument("--snapshot", type=Path, default=CHECKOUT / "data" / "SNAPSHOT.md")
    args = p.parse_args(argv)
    judging = args.judging if args.judging is not None else args.snapshot.parent / snap.JUDGING_DIR
    if args.public is None:
        args.public = data_dir() / "exports" / args.run_id if args.run_id else CHECKOUT / "web" / "public" / "data"

    if args.verify:
        problems = snap.check_committed(args.snapshot.read_text() if args.snapshot.exists() else "", judging)
        for line in problems:
            print(f"snapshot: {line}", file=sys.stderr)
        print("snapshot: the committed judging section and judge-mode files are consistent" if not problems else "snapshot: tag is NOT consistent")
        return 1 if problems else 0
    if args.freeze_judge or args.check_frozen:
        text = args.snapshot.read_text() if args.snapshot.exists() else ""
        if args.freeze_judge:
            copied = snap.freeze_judge(args.public, text, judging)
            print(f"snapshot: froze {len(copied)} judge-mode files into {args.public / snap.FROZEN_DIR}")
            return 0
        problems = snap.check_frozen(args.public, text)
        for line in problems:
            print(f"snapshot: {line}", file=sys.stderr)
        print("snapshot: frozen judge-mode files match the judging section" if not problems else "snapshot: frozen files do not match")
        return 1 if problems else 0
    processed = args.processed if args.processed is not None else data_dir() / "processed"
    raw = args.raw if args.raw is not None else processed.parent / "raw"
    current = args.snapshot.read_text() if args.snapshot.exists() else ""
    if args.run_id:
        snap.check_run(args.public, processed, args.run_id)
    tag, stage = args.tag, args.stage
    if args.check:  # compare against what the section recorded, unless the caller says otherwise
        rec_tag, rec_stage = snap.recorded_tag_and_stage(current)
        tag, stage = tag or rec_tag, stage or rec_stage
    stage = (stage or "provisional") if args.run_id else None
    section = snap.build(args.public, processed, args.data_end, tag, raw, run_id=args.run_id, stage=stage)
    if args.check:
        same = snap.extract_section(current) == section
        print("snapshot: files match the judging section" if same else "snapshot: files differ from the judging section (or it is missing)")
        return 0 if same else 1
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    new_text = snap.upsert_section(current, section)
    if args.run_id:
        copied = snap.commit_judging(args.public, judging, new_text)
        print(f"snapshot: copied {len(copied)} judge-mode files into {judging}")
    args.snapshot.write_text(new_text)
    tag = tag or snap.default_tag(args.data_end or snap.data_end_of(args.public), stage)
    print(f"snapshot: wrote the judging section of {args.snapshot}")
    print(f"snapshot: next, the owner tags the release: git tag -a {tag} -m 'Judging snapshot' && git push origin {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
