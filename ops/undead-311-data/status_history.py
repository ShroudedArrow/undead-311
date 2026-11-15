"""Helper for the nightly refresh template (standard library only). REQ-OPS-NIGHTLY.3, REQ-OPS-ALERT.1.

The data repo's `nightly.yml` checks out the judged repo at the frozen tag and runs this file from there. Four commands:

  check   exit 1 unless the status file exists, parses and says `ok: true` (nothing is deployed from a failed run).
  record  after a failed night, append one entry `{at, ok: false, stage, run_url}` to the failure-history file.
  merge   before a successful deploy, copy the last failure entries into `status.json` under `history`, so the site
          shows that a night failed even though the deploy that followed succeeded.
  clear   after that successful deploy, empty the failure-history file.

The failure-history file lives as an asset of the GitHub Release `nightly-state` in the data repo (the workflow uploads
and downloads it). It holds no secret and no personal data: a time, a stage name and the run URL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

KEEP = 10
STAGES = ("checkout", "download", "pipeline", "check", "build", "deploy", "release")


def read_json(path: Path, default):
    """The parsed JSON in `path`, or `default` when the file is missing or damaged."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    """Atomic write: a temp file in the same folder, then a rename (a reader never sees half a file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_history(path: Path) -> list[dict]:
    """The failure entries in `path`: a list of objects; anything else counts as empty."""
    data = read_json(path, [])
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def failed_stage(outcomes: dict[str, str]) -> str:
    """The first stage, in pipeline order, whose outcome is not `success`; `unknown` when none is named."""
    for stage in STAGES:
        state = outcomes.get(stage)
        if state is not None and state not in ("success", "skipped", ""):
            return stage
    return "unknown"


def parse_outcomes(pairs: list[str]) -> dict[str, str]:
    """`pipeline=failure deploy=skipped` -> {"pipeline": "failure", "deploy": "skipped"}."""
    out: dict[str, str] = {}
    for p in pairs:
        name, sep, state = p.partition("=")
        if sep and name:
            out[name] = state
    return out


def record(history: list[dict], stage: str, run_url: str, at: str, keep: int = KEEP) -> list[dict]:
    """REQ-OPS-NIGHTLY.3: one failure entry appended; only the newest `keep` entries are kept."""
    entry = {"at": at, "ok": False, "stage": stage, "run_url": run_url}
    return [*history, entry][-keep:]


def merge(status: dict, history: list[dict], keep: int = KEEP) -> dict:
    """REQ-OPS-NIGHTLY.3: the status of this (good) run plus the failures since the last good deploy."""
    merged = dict(status)
    merged["history"] = history[-keep:]
    return merged


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--status", required=True, type=Path)
    r = sub.add_parser("record")
    r.add_argument("--history", required=True, type=Path)
    r.add_argument("--run-url", default="")
    r.add_argument("--outcomes", nargs="*", default=[], help="stage=outcome pairs, e.g. pipeline=failure")
    r.add_argument("--at", default="")
    m = sub.add_parser("merge")
    m.add_argument("--status", required=True, type=Path)
    m.add_argument("--history", required=True, type=Path)
    k = sub.add_parser("clear")
    k.add_argument("--history", required=True, type=Path)
    args = p.parse_args(argv)

    if args.cmd == "check":
        status = read_json(args.status, None)
        if not isinstance(status, dict) or status.get("ok") is not True:
            print(f"status_history: {args.status} is missing or not ok; nothing will be deployed", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "record":
        stage = failed_stage(parse_outcomes(args.outcomes))
        write_json(args.history, record(load_history(args.history), stage, args.run_url, args.at or now()))
        return 0
    if args.cmd == "merge":
        status = read_json(args.status, None)
        if not isinstance(status, dict):
            print(f"status_history: {args.status} is missing or damaged", file=sys.stderr)
            return 1
        write_json(args.status, merge(status, load_history(args.history)))
        return 0
    write_json(args.history, [])
    return 0


if __name__ == "__main__":
    sys.exit(main())
