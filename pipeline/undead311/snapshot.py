"""Frozen judging snapshot (REQ-OPS-SNAP.1, REQ-OPS-SNAP.2).

`make snapshot` hashes the files the site serves (`web/public/data/**`) and the processed files the pipeline wrote
(`$DATA_DIR/processed`: Parquet and `run_report.json`), and writes the table into the judging section of
`data/SNAPSHOT.md`. The section sits between two marker comments, so the download table above it is never touched, and
`download.py` keeps the section when it rewrites the file.

Reproducible (check O4): the output depends only on the file bytes, the data end date and the tag name. No wall clock,
no absolute path and no file mtime goes into it. The DuckDB file is left out because DuckDB does not write the same bytes
for the same data twice. The script never creates or pushes a git tag: that is the owner's step (printed at the end).
After the freeze the site keeps serving this snapshot even when the nightly refresh fails or is switched off, because
the data is part of the deployed site and Netlify keeps the last good deploy (REQ-OPS-SNAP.2).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

BEGIN = "<!-- BEGIN judging snapshot (written by make snapshot; do not edit) -->"
END = "<!-- END judging snapshot -->"
PROCESSED_SUFFIXES = {".parquet"}
PROCESSED_NAMES = {"run_report.json"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(public_dir: Path, processed_dir: Path | None) -> list[tuple[str, int, str]]:
    """(label, bytes, sha256) for every served data file and processed file, sorted by label.

    Labels are `web/public/data/<relative path>` and `processed/<relative path>` with `/` separators, so the table does
    not depend on where the checkout lives."""
    rows: list[tuple[str, int, str]] = []
    if public_dir.is_dir():
        for p in public_dir.rglob("*"):
            if p.is_file():
                rows.append((f"web/public/data/{p.relative_to(public_dir).as_posix()}", p.stat().st_size, sha256_file(p)))
    if processed_dir is not None and processed_dir.is_dir():
        for p in processed_dir.rglob("*"):
            if p.is_file() and (p.suffix in PROCESSED_SUFFIXES or p.name in PROCESSED_NAMES):
                rows.append((f"processed/{p.relative_to(processed_dir).as_posix()}", p.stat().st_size, sha256_file(p)))
    return sorted(rows)


def combined_hash(rows: list[tuple[str, int, str]]) -> str:
    """One hash over the whole table: the sha256 of the sorted `label sha256` lines."""
    text = "".join(f"{label} {digest}\n" for label, _, digest in sorted(rows))
    return hashlib.sha256(text.encode()).hexdigest()


def default_tag(data_end: str) -> str:
    return f"judged-{data_end}"


def render_section(rows: list[tuple[str, int, str]], data_end: str, tag: str) -> str:
    """The judging section, markers included."""
    lines = [
        BEGIN,
        "## Judging snapshot",
        "",
        f"Data through: {data_end}. The site, the video and the README numbers use these files.",
        f"Git tag: `{tag}` (created by the owner, see below). Files hashed: {len(rows)}. Combined sha256: `{combined_hash(rows)}`.",
        "",
        "| file | bytes | sha256 |",
        "|---|---|---|",
        *[f"| {label} | {size} | {digest} |" for label, size, digest in rows],
        "",
        "The DuckDB file is not listed: DuckDB does not write identical bytes for identical data. The raw downloads above are listed with their hashes.",
        "",
        "Owner steps after `make snapshot` (the script never tags or pushes):",
        "",
        f"1. Commit `data/SNAPSHOT.md` and the files under `web/public/data/`, then run `git tag -a {tag} -m \"Judging snapshot, data through {data_end}\"` and `git push origin {tag}`.",
        f"2. In `ShroudedArrow/undead-311-data`, set the variable `JUDGED_TAG` to `{tag}` (see `ops/undead-311-data/README.md`).",
        "3. To check a checkout against this table later, run `make snapshot-check`.",
        END,
    ]
    return "\n".join(lines) + "\n"


def upsert_section(text: str, section: str) -> str:
    """`text` with the judging section replaced, or appended when there is none. Idempotent."""
    start, end = text.find(BEGIN), text.find(END)
    if start != -1 and end > start:
        tail = text[end + len(END):].lstrip("\n")
        return text[:start] + section + (("\n" + tail) if tail else "")
    base = text.rstrip("\n")
    return (base + "\n\n" if base else "") + section


def extract_section(text: str) -> str | None:
    """The judging section (markers included) in `text`, or None."""
    start, end = text.find(BEGIN), text.find(END)
    if start == -1 or end < start:
        return None
    return text[start:end + len(END)] + "\n"


def data_end_of(public_dir: Path) -> str:
    """`data_end` from status.json, the date the data runs through."""
    try:
        status = json.loads((public_dir / "status.json").read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"snapshot: cannot read {public_dir / 'status.json'}; run `make pipeline` first ({exc})") from exc
    end = status.get("data_end")
    if not isinstance(end, str) or not end:
        raise SystemExit("snapshot: status.json has no data_end; pass --data-end YYYY-MM-DD")
    return end


def build(public_dir: Path, processed_dir: Path | None, data_end: str | None, tag: str | None) -> str:
    end = data_end or data_end_of(public_dir)
    return render_section(collect(public_dir, processed_dir), end, tag or default_tag(end))
