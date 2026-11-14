"""Command line: `python -m undead311 pipeline [--sample]` (REQ-ING-NIGHTLY.1-2).

`pipeline` runs load, normalize, crosswalk, clean, Coroner join, detect, export on `$DATA_DIR/raw/`.
`pipeline --sample` runs the same path on `data/sample/` into `$DATA_DIR/processed-sample/` with no network.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="undead311")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pipeline", help="ingest -> detect -> export")
    p.add_argument("--sample", action="store_true", help="run on data/sample/ (no network, no raw data needed)")
    p.add_argument("--out", default=None, help="export folder (default web/public/data in the repo checkout)")
    c = sub.add_parser("coroner-eval", help="Coroner accuracy vs. the hand labels, written to docs/VALIDATION.md")
    c.add_argument("--labels-dir", default=None, help="folder with coroner_labels.csv (default data/labels in the checkout)")
    c.add_argument("--validation", default=None, help="markdown file to update (default docs/VALIDATION.md)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "pipeline":
        from undead311.pipeline import run_pipeline

        report = run_pipeline(sample=args.sample, out_dir=args.out)
        print(report.summary())
        return 0 if report.ok else 1
    if args.command == "coroner-eval":
        from pathlib import Path

        from undead311.coroner.eval import run
        from undead311.paths import worktree_root

        root = worktree_root()
        labels_dir = Path(args.labels_dir) if args.labels_dir else root / "data" / "labels"
        validation = Path(args.validation) if args.validation else root / "docs" / "VALIDATION.md"
        code, message = run(labels_dir, validation)
        print(message)
        return code
    return 2
