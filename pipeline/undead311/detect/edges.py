"""Candidate edges between cases (REQ-DET-MATCH.4).

An edge is an unordered pair of same-family cases that (1) match by `match()` and (2) are time-related in at least
one way the detector needs:
  (a) member edge: both closed and opened within INCIDENT_MAX_SPAN_DAYS of each other;
  (b) re-report edge: one is closed and the other opens after that close, within WINDOW_DAYS plus
      INCIDENT_MAX_SPAN_DAYS (an incident closes up to that long after one of its members, REQ-DET-1.2);
  (c) mirror edge: different systems and opened within MIRROR_WINDOW_HOURS.
`sql_edges` finds candidates with a grid-bucket join in DuckDB (never all pairs) and classifies them with `match()`.
`brute_edges` is the reference used by tests. Both return {(id_a, id_b): Match} with id_a < id_b.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np

from undead311.detect.match import EARTH_RADIUS_M, case_distance_m, match
from undead311.detect.model import Case, Match, to_us
from undead311.detect.params import DEFAULT, Params

COARSE_MARGIN_M = 1.0
M_PER_DEG_LAT = 111_320.0
GRID_COS_LAT = math.cos(math.radians(42.45))  # widest-cell latitude of the Boston box


def _us(days: float = 0.0, hours: float = 0.0) -> int:
    return round((days * 86400 + hours * 3600) * 1_000_000)


def time_related(a: Case, b: Case, p: Params = DEFAULT) -> bool:
    """The three time conditions above, in exact integer microseconds (same logic as the SQL join)."""
    oa, ob, ca, cb = a.open_us, b.open_us, a.close_us, b.close_us
    if ca is not None and cb is not None and abs(oa - ob) <= _us(p.INCIDENT_MAX_SPAN_DAYS):
        return True
    win = _us(p.WINDOW_DAYS + p.INCIDENT_MAX_SPAN_DAYS)
    if ca is not None and ca < ob <= ca + win:
        return True
    if cb is not None and cb < oa <= cb + win:
        return True
    return a.system != b.system and abs(oa - ob) <= _us(hours=p.MIRROR_WINDOW_HOURS)


def _key(a: Case, b: Case) -> tuple[str, str]:
    return (a.id, b.id) if a.id < b.id else (b.id, a.id)


def brute_edges(cases: list[Case], p: Params = DEFAULT) -> dict[tuple[str, str], Match]:
    """Reference edge generator: numpy distance and family prefilter, then the exact rules in Python."""
    n = len(cases)
    if n < 2:
        return {}
    lat = np.radians(np.array([c.lat for c in cases]))
    lon = np.radians(np.array([c.lon for c in cases]))
    fam = np.array([c.type_family for c in cases], dtype=object)
    maxd = p.max_match_dist_m + COARSE_MARGIN_M
    out: dict[tuple[str, str], Match] = {}
    for i in range(n - 1):
        dphi = lat[i + 1 :] - lat[i]
        dl = lon[i + 1 :] - lon[i]
        h = np.sin(dphi / 2) ** 2 + np.cos(lat[i]) * np.cos(lat[i + 1 :]) * np.sin(dl / 2) ** 2
        d = 2 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(h)))
        for j in np.nonzero((d <= maxd) & (fam[i + 1 :] == fam[i]))[0]:
            other = cases[i + 1 + int(j)]
            if time_related(cases[i], other, p):
                m = match(cases[i], other, p)
                if m is not None:
                    out[_key(cases[i], other)] = m
    return out


def sql_edges(
    con: duckdb.DuckDBPyConnection, cases: list[Case], p: Params = DEFAULT, table: str = "edge_input"
) -> dict[tuple[str, str], Match]:
    """Grid-bucket join in DuckDB for coarse candidates, then exact classification with `match()` (REQ-DET-MATCH.4)."""
    if len(cases) < 2:
        return {}
    by_id = {c.id: c for c in cases}
    cell_lat = (p.max_match_dist_m + COARSE_MARGIN_M) / M_PER_DEG_LAT
    cell_lon = (p.max_match_dist_m + COARSE_MARGIN_M) / (M_PER_DEG_LAT * GRID_COS_LAT)
    con.execute(f"drop table if exists {table}")
    con.execute(
        f"create temp table {table}(id varchar, fam varchar, sys varchar, lat double, lon double, "
        "o bigint, c bigint)"
    )
    con.executemany(
        f"insert into {table} values (?,?,?,?,?,?,?)",
        [(c.id, c.type_family, c.system, c.lat, c.lon, c.open_us, c.close_us) for c in cases],
    )
    span, mir = _us(p.INCIDENT_MAX_SPAN_DAYS), _us(hours=p.MIRROR_WINDOW_HOURS)
    win = _us(p.WINDOW_DAYS + p.INCIDENT_MAX_SPAN_DAYS)
    maxd = p.max_match_dist_m + COARSE_MARGIN_M
    rows = con.execute(f"""
        with g as (select *, floor(lat / {cell_lat})::bigint as cy, floor(lon / {cell_lon})::bigint as cx from {table}),
        nb as (select g.*, dx, dy from g, (select unnest([-1, 0, 1]) as dx) a, (select unnest([-1, 0, 1]) as dy) b)
        select a.id, b.id
        from g a join nb b on a.fam = b.fam and a.cx = b.cx + b.dx and a.cy = b.cy + b.dy and a.id < b.id
        where 2 * {EARTH_RADIUS_M} * asin(least(1.0, sqrt(
                  pow(sin(radians(b.lat - a.lat) / 2), 2)
                  + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2)))) <= {maxd}
          and ((a.c is not null and b.c is not null and abs(a.o - b.o) <= {span})
               or (a.c is not null and b.o > a.c and b.o <= a.c + {win})
               or (b.c is not null and a.o > b.c and a.o <= b.c + {win})
               or (a.sys <> b.sys and abs(a.o - b.o) <= {mir}))
    """).fetchall()  # fmt: skip
    out: dict[tuple[str, str], Match] = {}
    for ia, ib in rows:
        a, b = by_id[ia], by_id[ib]
        m = match(a, b, p)
        if m is not None:
            out[(ia, ib)] = m
    con.execute(f"drop table {table}")
    return out


__all__ = ["brute_edges", "case_distance_m", "sql_edges", "time_related", "to_us"]
