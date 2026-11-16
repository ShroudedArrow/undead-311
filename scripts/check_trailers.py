"""Check that commits carry the Kiro-Agent and Kiro-Run trailers (structure.md).

Usage: python3 scripts/check_trailers.py <rev-range> [--require-run RUN_ID]
Exempt (owner decision, ops#125): merge commits (a merge is not an agent's change) and commits authored by the owner
(ShroudedArrow: web edits). Agent commits are never exempt, so one without trailers still fails. History is never rewritten.
Prints one line per commit and exits 1 if any checked commit lacks a trailer (or has a different Kiro-Run).
"""

from __future__ import annotations

import subprocess
import sys


def trailers(sha: str) -> dict[str, str]:
    out = subprocess.run(["git", "log", "-1", "--format=%(trailers:only,unfold)", sha],
                         capture_output=True, text=True, check=True).stdout
    return {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in out.splitlines() if ":" in ln)}


OWNER = "ShroudedArrow"


def is_owner(name: str, email: str) -> bool:
    """True for a commit authored by the owner's GitHub account (ops#125); an agent's name or email never matches."""
    return name.strip() == OWNER or email.strip().lower().split("@")[0].endswith("+" + OWNER.lower())


def author(sha: str) -> tuple[str, str]:
    out = subprocess.run(["git", "log", "-1", "--format=%an%x00%ae", sha], capture_output=True, text=True, check=True).stdout
    name, _, email = out.rstrip("\n").partition("\0")
    return name, email


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rng = sys.argv[1]
    need_run = sys.argv[sys.argv.index("--require-run") + 1] if "--require-run" in sys.argv else None
    shas = subprocess.run(["git", "rev-list", "--reverse", "--no-merges", rng], capture_output=True, text=True, check=True).stdout.split()
    bad = 0
    skipped = 0
    for sha in shas:
        if is_owner(*author(sha)):
            skipped += 1
            print(f"EXEMPT {sha[:9]} authored by {OWNER}")
            continue
        t = trailers(sha)
        subj = subprocess.run(["git", "log", "-1", "--format=%s", sha], capture_output=True, text=True, check=True).stdout.strip()
        ok = bool(t.get("Kiro-Agent")) and bool(t.get("Kiro-Run")) and (need_run is None or t.get("Kiro-Run") == need_run)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {sha[:9]} Kiro-Agent={t.get('Kiro-Agent', '-')} Kiro-Run={t.get('Kiro-Run', '-')} | {subj}")
    checked = len(shas) - skipped
    print(f"{checked - bad}/{checked} checked commits carry both trailers ({skipped} owner-authored exempt)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
