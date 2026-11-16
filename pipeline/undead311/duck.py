"""DuckDB connection settings for every connection the pipeline opens (REQ-OPS-DUCK.1-3).

DuckDB's defaults are 80% of RAM, one spill folder beside the database file (or `.tmp` in the working directory for an
in-memory connection) and no cap on that folder. A full-data run needs the opposite: headroom for the Python stages
that run in the same process, and a spill folder under `$DATA_DIR` (the sandbox wipes `/tmp` between commands).
`configure(con)` sets four values; `connect()` opens a connection and configures it. Every pipeline entry point
(ingest, export, sample builders, fixtures) goes through these two functions.

Defaults and overrides (an environment value wins over the default):
  memory_limit             65% of RAM (the cgroup limit when that is lower)   UNDEAD311_DUCKDB_MEMORY_LIMIT, e.g. "12GB"
  threads                  CPUs this process may use                            UNDEAD311_DUCKDB_THREADS
  temp_directory           $DATA_DIR/tmp (tech.md fallback when DATA_DIR is unusable)   UNDEAD311_DUCKDB_TEMP_DIR
  max_temp_directory_size  20GB                                                 UNDEAD311_DUCKDB_MAX_TEMP
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import duckdb

from undead311.paths import data_dir

MEMORY_SHARE = 0.65
DEFAULT_MAX_TEMP = "20GB"
ENV_MEMORY = "UNDEAD311_DUCKDB_MEMORY_LIMIT"
ENV_THREADS = "UNDEAD311_DUCKDB_THREADS"
ENV_TEMP_DIR = "UNDEAD311_DUCKDB_TEMP_DIR"
ENV_MAX_TEMP = "UNDEAD311_DUCKDB_MAX_TEMP"
_MEMINFO = Path("/proc/meminfo")
_CGROUP_FILES = (Path("/sys/fs/cgroup/memory.max"), Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"))


def total_memory_bytes(
    meminfo: Path = _MEMINFO, cgroup_files: tuple[Path, ...] = _CGROUP_FILES
) -> int | None:
    """RAM this process can use: MemTotal, or the cgroup limit when that is a smaller number. None when unreadable."""
    total: int | None = None
    try:
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError, IndexError):
        pass
    for f in cgroup_files:
        try:
            raw = f.read_text().strip()
            limit = int(raw) if raw.isdigit() else None  # "max" means no limit
        except (OSError, ValueError):
            continue
        if limit and (total is None or limit < total):
            total = limit
    return total


def cpu_count() -> int:
    """CPUs this process may run on (affinity-aware), at least 1."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def default_memory_limit(total: int | None) -> str | None:
    """`65%` of `total` bytes as a DuckDB size string, or None when the total is unknown (DuckDB's default stays)."""
    if not total:
        return None
    return f"{max(1, int(total * MEMORY_SHARE) // (1 << 20))}MiB"


def settings(
    env: Mapping[str, str] | None = None, temp_dir: str | Path | None = None, total: int | None = None
) -> dict[str, str]:
    """The four settings as DuckDB strings. `memory_limit` is left out when the machine's RAM cannot be read."""
    env = os.environ if env is None else env
    out: dict[str, str] = {}
    memory = env.get(ENV_MEMORY) or default_memory_limit(total if total is not None else total_memory_bytes())
    if memory:
        out["memory_limit"] = memory
    out["threads"] = str(int(env[ENV_THREADS])) if env.get(ENV_THREADS) else str(cpu_count())
    out["temp_directory"] = str(env.get(ENV_TEMP_DIR) or temp_dir or (data_dir(quiet=True) / "tmp"))
    out["max_temp_directory_size"] = env.get(ENV_MAX_TEMP) or DEFAULT_MAX_TEMP
    return out


def configure(
    con: duckdb.DuckDBPyConnection, temp_dir: str | Path | None = None, env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Apply the settings to `con` and return what was set. The spill folder is created first. REQ-OPS-DUCK.1-2."""
    values = settings(env, temp_dir)
    Path(values["temp_directory"]).mkdir(parents=True, exist_ok=True)
    for name, value in values.items():
        con.execute(f"set {name} = ?", [value])
    return values


def connect(
    database: str | Path = ":memory:", read_only: bool = False, temp_dir: str | Path | None = None
) -> duckdb.DuckDBPyConnection:
    """`duckdb.connect` followed by `configure`. REQ-OPS-DUCK.3."""
    con = duckdb.connect(str(database), read_only=read_only)
    configure(con, temp_dir)
    return con
