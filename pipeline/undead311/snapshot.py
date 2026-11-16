"""Frozen judging snapshot (REQ-OPS-SNAP.1, REQ-OPS-SNAP.2).

`make snapshot` hashes what a run actually leaves behind (the pipeline writes DuckDB, not Parquet; see docs/DECISIONS.md):
the raw input files (`$DATA_DIR/raw`), the row count of every table in `processed/undead311.duckdb`, `run_report.json`,
and every file the site serves (`web/public/data/**`). It writes the table into the judging section of `data/SNAPSHOT.md`. The section sits between two marker comments, so the download table above it is never touched, and
`download.py` keeps the section when it rewrites the file.

Reproducible (check O4): the output depends only on the file bytes, the data end date and the tag name. No wall clock,
no absolute path and no file mtime goes into it. The DuckDB file is left out because DuckDB does not write the same bytes
for the same data twice. The script never creates or pushes a git tag: that is the owner's step (printed at the end).
Judge mode on the frozen snapshot (REQ-OPS-SNAP.2). The nightly refresh rewrites `stats/judge_tour.json`, `points.json`
and the card shards from fresh data, so the files judge mode reads would drift from the table above after one good night.
`freeze_judge` therefore copies the tour file, the points file and the shards of the three tour zombies into
`web/public/data/frozen/` BEFORE the pipeline runs, and only if each file's sha256 equals its row in the judging section
(a tag whose files differ from the table is refused). The pipeline never writes `frozen/` (the exporter removes only files
it owns: cards/ and stats/), `collect` leaves the folder out of the table, and `check_frozen` re-verifies the copies in the
built site (`web/dist/data/frozen/`) against the table before the deploy. A failed night then keeps the last good deploy,
whose `frozen/` folder is still the snapshot's. The web app reads judge mode from `frozen/` (handoff to:web, ops#161).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import duckdb

from undead311.duck import connect

BEGIN = "<!-- BEGIN judging snapshot (written by make snapshot; do not edit) -->"
END = "<!-- END judging snapshot -->"
PROCESSED_NAMES = {"run_report.json"}
DUCKDB_FILE = "undead311.duckdb"
COUNTS_LABEL = f"processed/{DUCKDB_FILE}#table-row-counts"  # a hashed text of `table<TAB>rows` lines (REQ-OPS-SNAP.1)
RAW_PREFIX = "raw/"
FROZEN_DIR = "frozen"                      # under web/public/data; judge mode's copy of the snapshot (REQ-OPS-SNAP.2)
JUDGE_TOUR = "stats/judge_tour.json"
POINTS = "points.json"
PUBLIC_PREFIX = "web/public/data/"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def table_row_counts(db_path: Path) -> dict[str, int]:
    """Row count of every base table in the DuckDB file, by table name (sorted); bookkeeping tables (`_...`) are left out. {} when the file is missing or unreadable.

    The file is opened read-only, so it can be checked while no run is writing it."""
    if not Path(db_path).is_file():
        return {}
    try:
        con = connect(db_path, read_only=True)
    except duckdb.Error:
        return {}
    try:
        tables = [r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = 'main' and table_type = 'BASE TABLE' "
            "and table_name not like '\\_%' escape '\\' order by table_name").fetchall()]  # fmt: skip
        return {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
    finally:
        con.close()


def counts_text(counts: dict[str, int]) -> str:
    return "".join(f"{t}\t{n}\n" for t, n in sorted(counts.items()))


def collect(public_dir: Path, processed_dir: Path | None, raw_dir: Path | None = None) -> list[tuple[str, int, str]]:
    """(label, bytes, sha256) for every raw input file, the DuckDB table row counts, `run_report.json` and every served
    data file, sorted by label.

    Labels are `raw/<name>`, `web/public/data/<relative path>` and `processed/<relative path>` with `/` separators, so the
    table does not depend on where the checkout lives. The DuckDB file is represented by one pseudo-file whose bytes are the
    `table<TAB>rows` lines (DuckDB does not write identical bytes for identical data, but the counts are stable)."""
    rows: list[tuple[str, int, str]] = []
    if public_dir.is_dir():
        for p in public_dir.rglob("*"):
            if p.is_file() and p.relative_to(public_dir).parts[0] != FROZEN_DIR:
                rows.append((f"web/public/data/{p.relative_to(public_dir).as_posix()}", p.stat().st_size, sha256_file(p)))
    if processed_dir is not None and processed_dir.is_dir():
        for p in processed_dir.rglob("*"):
            if p.is_file() and p.name in PROCESSED_NAMES:
                rows.append((f"processed/{p.relative_to(processed_dir).as_posix()}", p.stat().st_size, sha256_file(p)))
        counts = table_row_counts(processed_dir / DUCKDB_FILE)
        if counts:
            text = counts_text(counts).encode()
            rows.append((COUNTS_LABEL, len(text), hashlib.sha256(text).hexdigest()))
    if raw_dir is not None and raw_dir.is_dir():
        for p in raw_dir.iterdir():
            if p.is_file() and not p.name.endswith(".part"):
                rows.append((f"{RAW_PREFIX}{p.name}", p.stat().st_size, sha256_file(p)))
    return sorted(rows)


def combined_hash(rows: list[tuple[str, int, str]]) -> str:
    """One hash over the whole table: the sha256 of the sorted `label sha256` lines."""
    text = "".join(f"{label} {digest}\n" for label, _, digest in sorted(rows))
    return hashlib.sha256(text.encode()).hexdigest()


def default_tag(data_end: str) -> str:
    return f"judged-{data_end}"


def render_section(
    rows: list[tuple[str, int, str]], data_end: str, tag: str, counts: dict[str, int] | None = None
) -> str:
    """The judging section, markers included. `counts` (DuckDB table row counts) is listed under the file table."""
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
        *(
            ["| DuckDB table | rows |", "|---|---|", *[f"| {t} | {n} |" for t, n in sorted(counts.items())], ""]
            if counts
            else []
        ),
        f"The DuckDB file itself is not hashed: DuckDB does not write identical bytes for identical data. Its table row counts are listed above and hashed as `{COUNTS_LABEL}`. The pipeline writes no Parquet.",
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


def status_data_end(public_dir: Path) -> str | None:
    """`data_end` from status.json, or None when the file is missing, damaged or has no date."""
    try:
        end = json.loads((public_dir / "status.json").read_text()).get("data_end")
    except (OSError, ValueError, AttributeError):
        return None
    return end if isinstance(end, str) and end else None


def build(
    public_dir: Path, processed_dir: Path | None, data_end: str | None, tag: str | None, raw_dir: Path | None = None
) -> str:
    """The judging section. REQ-OPS-SNAP.1: `--data-end` that disagrees with status.json is refused (ops#160), because
    the section would name a "Data through" date the hashed files do not run through."""
    actual = status_data_end(public_dir)
    if data_end and actual and data_end != actual:
        raise SystemExit(f"snapshot: --data-end {data_end} differs from data_end {actual} in {public_dir / 'status.json'}; "
                         "rerun without --data-end, or rebuild the data")
    end = data_end or data_end_of(public_dir)
    counts = table_row_counts(processed_dir / DUCKDB_FILE) if processed_dir is not None else {}
    return render_section(collect(public_dir, processed_dir, raw_dir), end, tag or default_tag(end), counts)


# ---- judge mode on the frozen snapshot (REQ-OPS-SNAP.2) -------------------------------------------------------------

def slug(text: str | None) -> str:
    """Card shard slug: the rule of `export.writers.slug` and `web/src/lib/shard.ts` (a test keeps the three equal)."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "unknown").lower()).strip("-") or "unknown"


def judge_files(public_dir: Path) -> list[str]:
    """Paths (relative to `public_dir`) judge mode reads: the tour file, the points file, and the card shard of each tour zombie."""
    tour = json.loads((public_dir / JUDGE_TOUR).read_text())
    points = json.loads((public_dir / POINTS).read_text())
    where = {zid: i for i, zid in enumerate(points["id"])}
    files = {JUDGE_TOUR, POINTS}
    for zid in tour["zombie_ids"]:
        if zid not in where:
            raise SystemExit(f"snapshot: tour zombie {zid} is not in {POINTS}")
        i = where[zid]
        files.add(f"cards/{slug(points['neighborhood'][i])}-{points['year'][i]}.json")
    return sorted(files)


def section_hashes(snapshot_text: str) -> dict[str, str]:
    """`{web/public/data/<path>: sha256}` from the judging section's table; empty when there is no section."""
    section = extract_section(snapshot_text)
    out: dict[str, str] = {}
    for line in (section or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith(PUBLIC_PREFIX):
            out[cells[0]] = cells[2]
    return out


def freeze_judge(public_dir: Path, snapshot_text: str) -> list[str]:
    """Copy the judge-mode files into `public_dir/frozen/`, each one only if its sha256 equals the judging table.

    Exits (SystemExit) when the section is missing or a file is absent or differs: freezing files the table does not
    describe would freeze the wrong thing. Returns the copied relative paths."""
    table = section_hashes(snapshot_text)
    if not table:
        raise SystemExit("snapshot: data/SNAPSHOT.md has no judging section; run `make snapshot` on the frozen data first")
    copied = []
    for rel in judge_files(public_dir):
        src = public_dir / rel
        want = table.get(PUBLIC_PREFIX + rel)
        if want is None or not src.is_file() or sha256_file(src) != want:
            raise SystemExit(f"snapshot: {rel} does not match the judging section of data/SNAPSHOT.md (tag and table disagree)")
        dest = public_dir / FROZEN_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied.append(rel)
    return copied


def check_frozen(public_dir: Path, snapshot_text: str) -> list[str]:
    """Problems with `public_dir/frozen/` against the judging table (empty when it is the snapshot): a missing folder,
    a file whose sha256 differs from its row, or a file with no row."""
    table = section_hashes(snapshot_text)
    root = public_dir / FROZEN_DIR
    files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
    if not table:
        return ["data/SNAPSHOT.md has no judging section"]
    if not files:
        return [f"{root} is missing or empty"]
    problems = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        want = table.get(PUBLIC_PREFIX + rel)
        if want is None:
            problems.append(f"{rel} has no row in the judging section")
        elif sha256_file(p) != want:
            problems.append(f"{rel} differs from the judging section")
    return problems
