"""Sensitivity runs (REQ-SENS-RUN.1-2): the detector at every grid point, stored in the DuckDB table `grid_runs`.

Grid (zombie-definition.md): matching in {segment, radius} x RADIUS_M in {15, 30, 50} x WINDOW_DAYS in {30, 60, 90} =
18 points, plus one run without Street Light Other (a migration catch-all, see the 2026-11-12 change-log entries) at the
default parameters. Every other parameter stays at the base value. The skeptic and confidence steps are not part of a
grid run: only counts leave it.

Candidate edges depend on matching and RADIUS_M but not on the window except through `time_related`, so edges are built
once per (matching, RADIUS_M) at the widest window and filtered by `time_related` for each window; the result is the
same edge set `sql_edges` gives at that window (tested).

Tables written by `store_grid`:
  grid_run_index(run_id, matching, radius_m, window_days, without_street_light_other, n_cases, headline, source_unknown,
                 city_rereport, sensitivity)  -- one row per run, also for a run with no zombie
  grid_runs(run_id, matching, radius_m, window_days, without_street_light_other, tier, family, department, zombies)
                 -- long format: one row per run, tier, type family and department with at least one zombie
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace

import duckdb

from undead311.detect.core import detect
from undead311.detect.edges import sql_edges, time_related
from undead311.detect.model import ZOMBIE_TIERS, Case, DetectionResult, Match
from undead311.detect.params import DEFAULT, Params

GRID_MATCHING = ("segment", "radius")
GRID_RADIUS_M = (15, 30, 50)
GRID_WINDOW_DAYS = (30, 60, 90)
CATCH_ALL_TYPE = "Street Light Other"
UNKNOWN = "(unknown)"
TIERS = ZOMBIE_TIERS


@dataclass(frozen=True)
class GridRun:
    run_id: str
    matching: str
    radius_m: float
    window_days: float
    without_street_light_other: bool
    n_cases: int
    counts: tuple[tuple[str, str, str, int], ...]  # (tier, family, department, zombies), sorted

    def total(self, tier: str) -> int:
        return sum(n for t, _f, _d, n in self.counts if t == tier)


def grid_points(base: Params = DEFAULT) -> list[Params]:
    """The 18 grid parameter sets, in a fixed order (REQ-SENS-RUN.1)."""
    return [
        replace(base, matching=m, RADIUS_M=r, WINDOW_DAYS=w)  # type: ignore[arg-type]
        for m in GRID_MATCHING for r in GRID_RADIUS_M for w in GRID_WINDOW_DAYS
    ]  # fmt: skip


def run_id(p: Params, without_street_light_other: bool = False) -> str:
    base = f"{p.matching}-r{p.RADIUS_M:g}-w{p.WINDOW_DAYS:g}"
    return base + ("-no-street-light-other" if without_street_light_other else "")


#: called once per run with (params, the run's cases, its detection result, without Street Light Other); lets the stats
#: stage compute per-run excess and stayed-fixed rate without a second detector pass (REQ-STAT-GRID.1)
Observer = Callable[[Params, list[Case], DetectionResult, bool], None]


def _count(
    cases: list[Case], p: Params, edges: dict[tuple[str, str], Match], without: bool, observer: Observer | None = None
) -> GridRun:
    result = detect(cases, p, edges)
    if observer is not None:
        observer(p, cases, result, without)
    counts = Counter((z.tier, z.type_family, z.department or UNKNOWN) for z in result.zombies)
    return GridRun(
        run_id(p, without), p.matching, p.RADIUS_M, p.WINDOW_DAYS, without, len(cases),
        tuple((t, f, d, n) for (t, f, d), n in sorted(counts.items())),
    )  # fmt: skip


def edges_for_window(
    wide: dict[tuple[str, str], Match], by_id: dict[str, Case], p: Params
) -> dict[tuple[str, str], Match]:
    """The edges of `wide` (built at a window at least as long) that are time-related at `p`."""
    return {k: m for k, m in wide.items() if time_related(by_id[k[0]], by_id[k[1]], p)}


def run_grid(
    con: duckdb.DuckDBPyConnection, cases: list[Case], base: Params = DEFAULT, observer: Observer | None = None
) -> list[GridRun]:
    """All 19 sensitivity runs, in a fixed order (REQ-SENS-RUN.1-2)."""
    cases = sorted((c for c in cases if c.scope_tier in ("core", "sensitivity")), key=lambda c: c.id)
    by_id = {c.id: c for c in cases}
    runs: list[GridRun] = []
    widest = max(GRID_WINDOW_DAYS)
    for matching in GRID_MATCHING:
        for radius in GRID_RADIUS_M:
            wide = sql_edges(con, cases, replace(base, matching=matching, RADIUS_M=radius, WINDOW_DAYS=widest))  # type: ignore[arg-type]
            for window in GRID_WINDOW_DAYS:
                p = replace(base, matching=matching, RADIUS_M=radius, WINDOW_DAYS=window)  # type: ignore[arg-type]
                runs.append(_count(cases, p, edges_for_window(wide, by_id, p), False, observer))
    kept = [c for c in cases if c.type_raw != CATCH_ALL_TYPE]  # REQ-SENS-RUN.2: default parameters, all tiers
    keep_ids = {c.id for c in kept}
    default_edges = edges_for_window(
        sql_edges(con, kept, replace(base, WINDOW_DAYS=widest)), {c.id: c for c in kept}, base
    ) if len(kept) > 1 else {}  # fmt: skip
    assert all(a in keep_ids and b in keep_ids for a, b in default_edges)
    runs.append(_count(kept, base, default_edges, True, observer))
    return runs


def store_grid(con: duckdb.DuckDBPyConnection, runs: list[GridRun]) -> None:
    """Create `grid_run_index` and `grid_runs` from `runs`."""
    con.execute("drop table if exists grid_run_index")
    con.execute("drop table if exists grid_runs")
    con.execute(
        "create table grid_run_index(run_id varchar, matching varchar, radius_m double, window_days double, "
        "without_street_light_other boolean, n_cases integer, headline integer, source_unknown integer, city_rereport integer, sensitivity integer)"
    )
    con.execute(
        "create table grid_runs(run_id varchar, matching varchar, radius_m double, window_days double, "
        "without_street_light_other boolean, tier varchar, family varchar, department varchar, zombies integer)"
    )
    con.executemany(
        "insert into grid_run_index values (?,?,?,?,?,?,?,?,?,?)",
        [(r.run_id, r.matching, r.radius_m, r.window_days, r.without_street_light_other, r.n_cases,
          *(r.total(t) for t in TIERS)) for r in runs],
    )  # fmt: skip
    rows = [(r.run_id, r.matching, r.radius_m, r.window_days, r.without_street_light_other, t, f, d, n)
            for r in runs for t, f, d, n in r.counts]  # fmt: skip
    if rows:
        con.executemany("insert into grid_runs values (?,?,?,?,?,?,?,?,?)", rows)
