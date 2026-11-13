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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "pipeline":
        from undead311.pipeline import run_pipeline

        report = run_pipeline(sample=args.sample, out_dir=args.out)
        print(report.summary())
        return 0 if report.ok else 1
    return 2
