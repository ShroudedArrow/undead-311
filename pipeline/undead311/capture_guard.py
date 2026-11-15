"""`make capture` runs only on the frozen judging snapshot (REQ-OPS-CAPTURE.1, REQ-OPS-SNAP.2, ops#200).

The screenshots, the time-lapse GIF and the judge-tour video must agree with the README and video numbers, so before
capture the files the site serves (`web/dist/data`) are compared with the judging section of `data/SNAPSHOT.md`. A
mismatch, or a missing section, stops the capture. The owner can override this for a development run (`--dev`); the
run then writes a NOT-SNAPSHOT marker into `docs/media/` so nobody mistakes those pictures for the judged ones.
"""

from __future__ import annotations

from pathlib import Path

from . import snapshot as snap

MARKER = "NOT-SNAPSHOT.txt"
MARKER_TEXT = (
    "These captures were made with `make capture CAPTURE_DEV=1` on data that does not match the judging snapshot "
    "(data/SNAPSHOT.md). Do not publish them. Rerun `make capture` on the frozen data.\n"
)


def check(served: Path, snapshot_text: str) -> list[str]:
    """Problems with the served data folder against the judging section; an empty list means it is the snapshot.

    REQ-OPS-CAPTURE.1: every non-frozen row of the table must exist in `served` with the same sha256, no served
    file may be missing from the table, and a `frozen/` folder (judge mode) must match too."""
    table = snap.section_hashes(snapshot_text)
    if not table:
        return ["data/SNAPSHOT.md has no judging section; run `make snapshot` on the frozen data first"]
    if not served.is_dir():
        return [f"{served} is missing; run `make build` first"]
    problems: list[str] = []
    seen: set[str] = set()
    for p in sorted(q for q in served.rglob("*") if q.is_file()):
        rel = p.relative_to(served)
        if rel.parts[0] == snap.FROZEN_DIR:
            continue
        label = snap.PUBLIC_PREFIX + rel.as_posix()
        seen.add(label)
        want = table.get(label)
        if want is None:
            problems.append(f"{rel.as_posix()} is served but has no row in the judging section")
        elif snap.sha256_file(p) != want:
            problems.append(f"{rel.as_posix()} differs from the judging section")
    problems += [
        f"{label.removeprefix(snap.PUBLIC_PREFIX)} is in the judging section but not served"
        for label in sorted(table)
        if label not in seen
    ]
    if (served / snap.FROZEN_DIR).is_dir():
        problems += [f"frozen: {line}" for line in snap.check_frozen(served, snapshot_text)]
    return problems


def apply_marker(media: Path, problems: list[str], dev: bool) -> int:
    """Exit code for `make capture`. 0 when the data is the snapshot (any old marker is removed) or when `dev` is set
    (the marker is written); 1 otherwise. REQ-OPS-CAPTURE.1."""
    marker = media / MARKER
    if not problems:
        marker.unlink(missing_ok=True)
        return 0
    if dev:
        media.mkdir(parents=True, exist_ok=True)
        marker.write_text(MARKER_TEXT, encoding="utf-8")
        return 0
    return 1
