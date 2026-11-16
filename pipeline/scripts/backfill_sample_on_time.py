"""Add the `on_time` column to data/sample/sample_311.csv without reselecting any row (REQ-STAT-SF.1, REQ-ING-SAMPLE).

Reads the raw CSVs through the pipeline's own load and normalize stages, so `on_time` is exactly what a full run
sees: true for ONTIME, false for OVERDUE, empty when unknown. Rows and their order are unchanged. The raw files may be newer than the sample: a row whose open or close time
no longer matches the raw file keeps an empty `on_time` (its flag may belong to a different closure).
Run: PYTHONPATH=pipeline python pipeline/scripts/backfill_sample_on_time.py [RAW_DIR]
(RAW_DIR defaults to $DATA_DIR/raw; the files must match data/SNAPSHOT.md.)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import download

from undead311.ingest.load import load
from undead311.ingest.normalize import normalize


def stamp(t) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""


def on_time_by_key(raw_dir: Path, snapshot_md: Path) -> dict[tuple[str, str], tuple[str, str, str]]:
    """(system, id) -> (open UTC, close UTC, 'true' | 'false' | '') from the normalized raw files."""
    con = duckdb.connect()
    load(con, raw_dir, snapshot_md)
    normalize(con)
    return {
        (system, str(cid)): (stamp(o), stamp(c), "" if v is None else str(bool(v)).lower())
        for cid, system, o, c, v in con.execute(
            "select id, system, open_time_utc, close_time_utc, on_time from cases_norm"
        ).fetchall()
    }


def backfill(sample: Path, raw_dir: Path, snapshot_md: Path) -> tuple[int, int]:
    """Rewrite `sample` with an `on_time` column. Returns (rows, rows with a known on_time)."""
    lookup = on_time_by_key(raw_dir, snapshot_md)
    with sample.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = [c for c in reader.fieldnames or [] if c != "on_time"] + ["on_time"]
        rows = list(reader)
    stale = 0
    for r in rows:
        o, c, v = lookup.get((r["system"], r["id"]), ("", "", ""))
        same = (o, c) == (r["open_time_utc"], r["close_time_utc"])
        stale += not same
        r["on_time"] = v if same else ""
    print(f"rows whose times differ from the raw files (on_time left empty): {stale}")
    with sample.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows), sum(1 for r in rows if r["on_time"])


def main() -> None:
    root = download.repo_root()
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else download.resolve_data_dir() / "raw"
    n, known = backfill(root / "data" / "sample" / "sample_311.csv", raw, root / "data" / "SNAPSHOT.md")
    print(f"rows={n} on_time_known={known}")


if __name__ == "__main__":
    main()
