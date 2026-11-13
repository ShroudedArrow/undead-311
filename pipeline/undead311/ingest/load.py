"""Load raw CSVs into DuckDB (REQ-ING-1).

Every column is read as text (`all_varchar`), so no value is lost or reinterpreted at load time. Files are read
only through DuckDB's `read_csv`, never row by row in Python (REQ-ING-1.3). A malformed row makes the load fail
loudly (no `ignore_errors`), so no row is dropped silently (REQ-ING-2.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

NEW_SYSTEM_FILE = "311_new_system.csv"
LEGACY_RE = re.compile(r"^311_(20\d{2})\.csv$")
SNAPSHOT_FILE_RE = re.compile(r"^\|\s*(311_[A-Za-z0-9_]+\.csv)\s*\|", re.MULTILINE)


class RawFileMissing(FileNotFoundError):
    """A raw file listed in data/SNAPSHOT.md is missing (REQ-ING-1.2)."""


@dataclass
class LoadReport:
    legacy_rows: int = 0
    new_rows: int = 0
    rows_by_file: dict[str, int] = field(default_factory=dict)


def expected_files(snapshot_md: Path) -> list[str]:
    """File names listed in the SNAPSHOT table (the 311 yearly files and the new-system file), sorted."""
    return sorted(set(SNAPSHOT_FILE_RE.findall(Path(snapshot_md).read_text())))


def _check_files(raw_dir: Path, names: list[str]) -> None:
    for name in names:
        if not (raw_dir / name).is_file():
            raise RawFileMissing(
                f"missing raw file {name} in {raw_dir}. Download it with `make data-download` (REQ-ING-1.2)."
            )


def _read(con: duckdb.DuckDBPyConnection, table: str, files: list[Path]) -> None:
    quoted = ", ".join("'" + str(f).replace("'", "''") + "'" for f in files)
    con.execute(f"drop table if exists {table}")
    con.execute(
        f"create table {table} as select * from read_csv([{quoted}], all_varchar=true, union_by_name=true, "
        "header=true, filename=true)"
    ).fetchall()  # drain the result so later work (UDF registration) can use the connection


def load(con: duckdb.DuckDBPyConnection, raw_dir: Path, snapshot_md: Path | None = None) -> LoadReport:
    """Create `raw_legacy` and `raw_new` from `raw_dir`; raise RawFileMissing naming the file (REQ-ING-1.1-2)."""
    raw_dir = Path(raw_dir)
    names = expected_files(snapshot_md) if snapshot_md else sorted(p.name for p in raw_dir.glob("311_*.csv"))
    if snapshot_md is None and not names:
        raise RawFileMissing(f"no 311_*.csv files in {raw_dir}. Download them with `make data-download`.")
    _check_files(raw_dir, names)
    legacy = [raw_dir / n for n in names if LEGACY_RE.match(n)]
    new = [raw_dir / n for n in names if n == NEW_SYSTEM_FILE]
    if not legacy or not new:
        raise RawFileMissing(
            f"need legacy yearly files and {NEW_SYSTEM_FILE} in {raw_dir}. Download them with `make data-download`."
        )
    _read(con, "raw_legacy", legacy)
    _read(con, "raw_new", new)
    report = LoadReport()
    for table in ("raw_legacy", "raw_new"):
        for fname, n in con.execute(f"select filename, count(*) from {table} group by 1 order by 1").fetchall():
            report.rows_by_file[Path(fname).name] = n
    report.legacy_rows = con.execute("select count(*) from raw_legacy").fetchone()[0]
    report.new_rows = con.execute("select count(*) from raw_new").fetchone()[0]
    return report
