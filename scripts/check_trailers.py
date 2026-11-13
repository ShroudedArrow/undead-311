"""Check that commits carry the Kiro-Agent and Kiro-Run trailers (structure.md).

Usage: python3 scripts/check_trailers.py <rev-range> [--require-run RUN_ID]
Merge commits are skipped (a merge is not an agent's change). Prints one line per commit and exits 1 if any commit lacks a trailer (or has a different Kiro-Run).
"""

from __future__ import annotations

import subprocess
import sys


def trailers(sha: str) -> dict[str, str]:
    out = subprocess.run(["git", "log", "-1", "--format=%(trailers:only,unfold)", sha],
                         capture_output=True, text=True, check=True).stdout
    return {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in out.splitlines() if ":" in ln)}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rng = sys.argv[1]
    need_run = sys.argv[sys.argv.index("--require-run") + 1] if "--require-run" in sys.argv else None
    shas = subprocess.run(["git", "rev-list", "--reverse", "--no-merges", rng], capture_output=True, text=True, check=True).stdout.split()
    bad = 0
    for sha in shas:
        t = trailers(sha)
        subj = subprocess.run(["git", "log", "-1", "--format=%s", sha], capture_output=True, text=True, check=True).stdout.strip()
        ok = bool(t.get("Kiro-Agent")) and bool(t.get("Kiro-Run")) and (need_run is None or t.get("Kiro-Run") == need_run)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {sha[:9]} Kiro-Agent={t.get('Kiro-Agent', '-')} Kiro-Run={t.get('Kiro-Run', '-')} | {subj}")
    print(f"{len(shas) - bad}/{len(shas)} commits carry both trailers")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
