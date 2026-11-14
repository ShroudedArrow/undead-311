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
    p.add_argument("--skip-grid", action="store_true", help="skip the 19 sensitivity runs (grid_runs); for quick local runs")
    p.add_argument("--out", default=None, help="export folder (default web/public/data in the repo checkout)")
    c = sub.add_parser("coroner-eval", help="Coroner accuracy vs. the hand labels, written to docs/VALIDATION.md")
    c.add_argument("--labels-dir", default=None, help="folder with coroner_labels.csv (default data/labels in the checkout)")
    c.add_argument("--validation", default=None, help="markdown file to update (default docs/VALIDATION.md)")
    v = sub.add_parser("validation-sample", help="draw the field-validation sample (REQ-STAT-VAL.1)")
    v.add_argument("--labels-dir", default=None, help="folder with validation_config.json (default data/labels in the checkout)")
    v.add_argument("--data", default=None, help="folder with zombies.json and status.json (default web/public/data)")
    f = sub.add_parser("validate", help="score the field labels into docs/VALIDATION.md and validation.json (REQ-STAT-VAL.2)")
    f.add_argument("--labels-dir", default=None, help="folder with validation_labels.csv (default data/labels in the checkout)")
    f.add_argument("--validation", default=None, help="markdown file to update (default docs/VALIDATION.md)")
    f.add_argument("--out", default=None, help="validation.json to write (default web/public/data/stats/validation.json)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "pipeline":
        from undead311.pipeline import run_pipeline

        report = run_pipeline(sample=args.sample, out_dir=args.out, grid=not args.skip_grid)
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
    if args.command in ("validation-sample", "validate"):
        import json
        from datetime import date
        from pathlib import Path

        from undead311.paths import worktree_root
        from undead311.stats import validation as val

        root = worktree_root()
        labels_dir = Path(args.labels_dir) if args.labels_dir else root / "data" / "labels"
        if args.command == "validation-sample":
            data = Path(args.data) if args.data else root / "web" / "public" / "data"
            end = date.today()
            try:
                end = date.fromisoformat(json.loads((data / "status.json").read_text())["data_end"])
            except (OSError, ValueError, KeyError):
                pass  # no status yet: the sample window ends today
            code, message = val.run_validation_sample(labels_dir, data / "zombies.json", end)
        else:
            md = Path(args.validation) if args.validation else root / "docs" / "VALIDATION.md"
            out = Path(args.out) if args.out else root / "web" / "public" / "data" / "stats" / "validation.json"
            version = "unknown"
            try:
                version = json.loads((out.parent.parent / "status.json").read_text())["data_version"]
            except (OSError, ValueError, KeyError):
                pass
            code, message = val.run_validate(labels_dir, md, out, version)
        print(message)
        return code
    return 2
