"""Stage runner: timing, peak memory, per-stage done-markers and resume (REQ-OPS-RUN.1-4).

`run_pipeline` is a list of stages. `StageRunner.run(name, fn)` runs one stage and returns its *delta*, a JSON-friendly
dict of report fields the stage produced (row counts, exclusions, warnings, ...); the caller merges it into the run report.

Two modes, one code path:
* Plain (no `stages_dir`): the stage runs and the delta is returned. Nothing is stored. This is the nightly and sample path.
* Persistent (`stages_dir` given, a file-backed connection): each stage runs inside ONE DuckDB transaction that also inserts
  its marker row into `_stage_done`, so a crash leaves either the whole stage and its marker or neither. A restart opens the
  same database file, finds the markers, skips the finished stages and returns their stored deltas, so the report is the
  same as in an uninterrupted run. After the commit a copy of the marker is written to
  `<stages_dir>/NN-<name>.done.json` for people to read, and the database is checkpointed.

`always(name, fn)` runs and logs a step every time (steps that rebuild Python-side state from the database, such as the
detector, or that write files into a staging folder); it has no marker.

A fingerprint (snapshot text, parameters, raw file sizes) is stored with the markers; `prepare` discards a partial build
whose fingerprint differs, so a restart never mixes stages from two different inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import duckdb

MARKER_TABLE = "_stage_done"
META_TABLE = "_run_meta"
FINGERPRINT_FILE = "fingerprint.txt"
COMPLETE_FILE = "complete.json"  # written when the whole run is swapped in, just before the database rename (REQ-OPS-RUN.8)


def rss_mb() -> float:
    """Resident set size of this process in MB (0 where /proc is unavailable)."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def process_peak_mb() -> float:
    """High-water mark of the whole process so far (never falls), in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class PeakSampler:
    """Samples RSS on a thread while a stage runs; `peak` is the highest sample (MB)."""

    def __init__(self, interval: float = 0.25):
        self.interval, self.peak = interval, rss_mb()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.peak = max(self.peak, rss_mb())

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, rss_mb())


def fingerprint(snapshot_text: str, params_json: str, raw_files: dict[str, int]) -> str:
    """Hash of everything a partial build depends on besides the code: the snapshot text, the parameters, raw file sizes."""
    payload = json.dumps(
        {"snapshot": snapshot_text, "params": params_json, "raw": sorted(raw_files.items())}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def prepare(stages_dir: Path, db_tmp: Path, fp: str, log: Callable[[str], None] = print) -> bool:
    """Decide whether a partial build in `db_tmp` can be resumed. Returns True when it can.

    A missing database, a missing or different fingerprint, or markers without a database all mean a fresh start: the
    partial database, its WAL and the marker files are removed. The fingerprint is (re)written either way."""
    stages_dir = Path(stages_dir)
    stages_dir.mkdir(parents=True, exist_ok=True)
    fp_file = stages_dir / FINGERPRINT_FILE
    same = fp_file.is_file() and fp_file.read_text().strip() == fp
    wal = db_tmp.with_name(db_tmp.name + ".wal")
    if same and db_tmp.is_file():
        log(f"resume: found a partial build ({db_tmp.name}) with the same inputs")
        return True
    if db_tmp.exists() or wal.exists() or any(stages_dir.glob("*.done.json")):
        why = "inputs changed" if fp_file.is_file() and not same else "no usable partial database"
        log(f"fresh start ({why}): discarding the partial build and its markers")
    for p in (db_tmp, wal, *stages_dir.glob("*.done.json"), stages_dir / COMPLETE_FILE):
        p.unlink(missing_ok=True)
    fp_file.write_text(fp + "\n")
    return False


def mark_complete(stages_dir: Path, fp: str) -> None:
    """Record that every stage finished and the outputs are swapped in (REQ-OPS-RUN.8). Written before the database
    rename: a process that dies right after the rename leaves this file and no partial database."""
    tmp = Path(stages_dir) / (COMPLETE_FILE + ".tmp")
    tmp.write_text(json.dumps({"fingerprint": fp}) + "\n")
    tmp.replace(Path(stages_dir) / COMPLETE_FILE)


def is_complete(stages_dir: Path, fp: str, db_tmp: Path, final: Path) -> bool:
    """True when a run with these inputs already finished: the marker names this fingerprint, the finished database is in
    place and no partial one is left. `prepare` would call that state "no usable partial database" and rebuild everything."""
    try:
        doc = json.loads((Path(stages_dir) / COMPLETE_FILE).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("fingerprint") == fp and Path(final).is_file() and not Path(db_tmp).exists()


class StageRunner:
    """Runs named stages with timing and peak memory, and (when persistent) skips the ones already done."""

    def __init__(
        self,
        stages_dir: Path | None = None,
        log: Callable[[str], None] = print,
        on_stage: Callable[[dict], None] | None = None,
    ):
        self.stages_dir = Path(stages_dir) if stages_dir else None
        self.log, self.on_stage = log, on_stage
        self.con: duckdb.DuckDBPyConnection | None = None
        self.records: list[dict] = []
        self._done: dict[str, dict] = {}
        self._n = 0
        self.current: str | None = None  # the stage that is running, or that raised (kept after an exception)

    @property
    def persistent(self) -> bool:
        return self.stages_dir is not None

    def attach(self, con: duckdb.DuckDBPyConnection) -> None:
        """Bind the connection; in persistent mode create the marker tables and load the markers already there."""
        self.con = con
        if not self.persistent:
            return
        con.execute(
            f"create table if not exists {MARKER_TABLE}(stage varchar primary key, seq integer, finished_utc varchar, "
            "seconds double, peak_rss_mb double, process_peak_mb double, rows varchar, delta varchar)"
        )
        con.execute(f"create table if not exists {META_TABLE}(key varchar primary key, value varchar)")
        for stage, seq, fin, sec, peak, ppeak, rows, delta in con.execute(
            f"select * from {MARKER_TABLE} order by seq"
        ).fetchall():
            self._done[stage] = {
                "stage": stage, "seq": seq, "finished_utc": fin, "seconds": sec, "peak_rss_mb": peak,
                "process_peak_mb": ppeak, "rows": json.loads(rows), "delta": json.loads(delta),
            }  # fmt: skip
        self._n = len(self._done)
        for rec in self._done.values():
            self._write_marker(rec)

    def done(self, name: str) -> bool:
        return name in self._done

    # ---- running ---------------------------------------------------------------------------------------------------

    def _table_rows(self, tables: tuple[str, ...]) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in tables:
            try:
                out[t] = self.con.execute(f'select count(*) from "{t}"').fetchone()[0]  # type: ignore[union-attr]
            except duckdb.Error:
                pass
        return out

    def _rows(self, tables: tuple[str, ...], delta: dict) -> dict[str, int]:
        """Row counts shown for a stage: its tables, the delta's `row_counts` and its `stage_rows` (not part of the report)."""
        return {**self._table_rows(tables), **delta.get("row_counts", {}), **delta.get("stage_rows", {})}

    def _write_marker(self, rec: dict) -> None:
        if self.stages_dir is None:
            return
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        path = self.stages_dir / f"{rec['seq']:02d}-{rec['stage']}.done.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)

    def _emit(self, rec: dict) -> None:
        self.records.append(rec)
        status = rec["status"]
        rows = ", ".join(f"{k}={v:,}" for k, v in rec["rows"].items())
        self.log(
            f"[stage] {rec['stage']:<26} {status:<8} {rec['seconds']:8.1f}s  peak {rec['peak_rss_mb']:8.0f} MB "
            f"(process high-water {rec['process_peak_mb']:.0f} MB)" + (f"  rows: {rows}" if rows else "")
        )
        if self.on_stage is not None and status == "done":
            try:
                self.on_stage(rec)
            except Exception as exc:  # noqa: BLE001 - a failed progress post never stops the run
                self.log(f"[stage] progress callback failed ({type(exc).__name__})")

    def run(self, name: str, fn: Callable[[], dict | None], tables: tuple[str, ...] = ()) -> dict:
        """Run stage `name` once. A stage already marked done in the database is skipped and its stored delta returned."""
        if name in self._done:
            rec = self._done[name]
            self._emit({**rec, "status": "skipped", "seconds": 0.0, "rows": rec["rows"]})
            return rec["delta"]
        started = time.time()
        self.current = name
        with PeakSampler() as sampler:
            if self.persistent:
                self.con.execute("begin")  # type: ignore[union-attr]
            try:
                delta = fn() or {}
                rows = self._rows(tables, delta)
                seconds = time.time() - started
                rec = {
                    "stage": name, "seq": self._n + 1, "finished_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "seconds": round(seconds, 2), "peak_rss_mb": round(max(sampler.peak, rss_mb()), 1),
                    "process_peak_mb": round(process_peak_mb(), 1), "rows": rows, "delta": delta,
                }  # fmt: skip
                if self.persistent:
                    self.con.execute(  # type: ignore[union-attr]
                        f"insert into {MARKER_TABLE} values (?,?,?,?,?,?,?,?)",
                        [name, rec["seq"], rec["finished_utc"], rec["seconds"], rec["peak_rss_mb"], rec["process_peak_mb"],
                         json.dumps(rows, sort_keys=True), json.dumps(delta, sort_keys=True)],
                    )  # fmt: skip
                    self.con.execute("commit")  # type: ignore[union-attr]
            except BaseException:
                if self.persistent:
                    try:
                        self.con.execute("rollback")  # type: ignore[union-attr]
                    except duckdb.Error:
                        pass
                raise
        rec["peak_rss_mb"] = round(max(rec["peak_rss_mb"], sampler.peak), 1)
        self._n += 1
        self.current = None
        self._done[name] = rec
        if self.persistent:
            self.con.execute("checkpoint")  # type: ignore[union-attr]
            self._write_marker(rec)
        self._emit({**rec, "status": "done"})
        return delta

    def always(self, name: str, fn: Callable[[], dict | None], tables: tuple[str, ...] = ()) -> dict:
        """Run `fn` every time (no marker); it is timed and logged like a stage."""
        started = time.time()
        self.current = name
        with PeakSampler() as sampler:
            delta = fn() or {}
        rows = self._rows(tables, delta)
        self.current = None
        self._emit({
            "stage": name, "seq": 0, "status": "done", "finished_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds": round(time.time() - started, 2), "peak_rss_mb": round(sampler.peak, 1),
            "process_peak_mb": round(process_peak_mb(), 1), "rows": rows, "delta": delta,
        })  # fmt: skip
        return delta
