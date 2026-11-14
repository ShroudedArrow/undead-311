#!/usr/bin/env python3
"""Compare Kiro Web's cloud-cache copies of workflows, agents, hooks and steering with the repo copies on main.

Kiro Web runs agents, hooks, steering and recipes from the cloud configuration, not from the repo (docs/DECISIONS.md,
2026-11-13). A repo change that was never re-synced runs stale, so any difference is a failure.

Usage:  python3 scripts/cloud_sync.py [--cloud DIR] [--ref REF] [--working-tree]
  --cloud DIR       cloud-cache folder holding agents/ hooks/ steering/ workflows/ (default: first existing of
                    $CLOUD_CONFIG_DIR, ~/.kiro/cloud-cache/resolved/config/user, /projects/.kiro/cloud-cache/resolved/config/user)
  --ref REF         git ref holding the repo copies (default: origin/main, else main)
  --working-tree    compare against the checked-out files instead of a ref
Exit code: 0 = identical, 1 = at least one difference (or a file on only one side), 2 = no cloud cache found.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ("workflows", "agents", "hooks", "steering")
CLOUD_CANDIDATES = (
    "~/.kiro/cloud-cache/resolved/config/user",
    "/projects/.kiro/cloud-cache/resolved/config/user",
)


def find_cloud_dir(explicit: str | None = None) -> Path | None:
    """First existing cloud-cache folder, or None."""
    options = [explicit or os.environ.get("CLOUD_CONFIG_DIR")] + list(CLOUD_CANDIDATES)
    for opt in options:
        if opt and Path(opt).expanduser().is_dir():
            return Path(opt).expanduser()
    return None


def _git(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def default_ref(root: Path = ROOT) -> str | None:
    for ref in ("origin/main", "main"):
        if _git("rev-parse", "--verify", "--quiet", ref, cwd=root).returncode == 0:
            return ref
    return None


def repo_files(directory: str, ref: str | None, root: Path = ROOT) -> dict[str, bytes]:
    """Files of .kiro/<directory> as committed at `ref`, or as checked out when ref is None."""
    out: dict[str, bytes] = {}
    if ref is None:
        base = root / ".kiro" / directory
        for p in sorted(base.glob("*")) if base.is_dir() else []:
            if p.is_file() and not p.name.startswith("."):
                out[p.name] = p.read_bytes()
        return out
    listing = _git("ls-tree", "--name-only", f"{ref}:.kiro/{directory}", cwd=root)
    for name in listing.stdout.decode().splitlines() if listing.returncode == 0 else []:
        if name.startswith("."):
            continue
        blob = _git("show", f"{ref}:.kiro/{directory}/{name}", cwd=root)
        if blob.returncode == 0:
            out[name] = blob.stdout
    return out


def cloud_files(cloud: Path, directory: str) -> dict[str, bytes]:
    base = cloud / directory
    return (
        {p.name: p.read_bytes() for p in sorted(base.glob("*")) if p.is_file() and not p.name.startswith(".")}
        if base.is_dir()
        else {}
    )


def diff_sets(repo: dict[str, bytes], cloud: dict[str, bytes]) -> list[str]:
    """Human-readable differences: files on one side only, and files whose bytes differ."""
    problems = []
    for name in sorted(set(repo) | set(cloud)):
        if name not in cloud:
            problems.append(f"{name}: in the repo, not in the cloud copy")
        elif name not in repo:
            problems.append(f"{name}: in the cloud copy, not in the repo")
        elif repo[name] != cloud[name]:
            problems.append(
                f"{name}: differs (repo {hashlib.sha256(repo[name]).hexdigest()[:8]}, cloud {hashlib.sha256(cloud[name]).hexdigest()[:8]})"
            )
    return problems


def compare(cloud: Path, ref: str | None, root: Path = ROOT) -> dict[str, list[str]]:
    """{ '<dir>': [problem, ...] } for every compared directory; empty lists mean identical."""
    return {d: [f"{d}/{p}" for p in diff_sets(repo_files(d, ref, root), cloud_files(cloud, d))] for d in DIRS}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cloud")
    ap.add_argument("--ref")
    ap.add_argument("--working-tree", action="store_true")
    a = ap.parse_args(argv)
    cloud = find_cloud_dir(a.cloud)
    if cloud is None:
        print("cloud-cache folder not found; nothing to compare (set CLOUD_CONFIG_DIR or pass --cloud)")
        return 2
    ref = None if a.working_tree else (a.ref or default_ref())
    if ref is None and not a.working_tree:
        print("no origin/main or main ref; comparing the working tree")
    result = compare(cloud, ref)
    bad = [p for ps in result.values() for p in ps]
    print(f"cloud copy: {cloud}\nrepo copy:  {ref or 'working tree'}")
    for d in DIRS:
        print(f"  {d}: {'identical' if not result[d] else str(len(result[d])) + ' difference(s)'}")
    for p in bad:
        print(f"  DIFF {p}")
    if bad:
        print(
            "RE-SYNC NEEDED: upload the repo copies in Kiro Web (Settings, Configuration Sync), then re-run this check."
        )
        return 1
    print("cloud copies match the repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
