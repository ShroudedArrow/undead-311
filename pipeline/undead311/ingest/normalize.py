"""Normalize both systems into one table `cases_norm` (REQ-ING-2, REQ-ING-TZ).

Legacy and new-system columns are mapped to the normalized schema of data-dictionary.md. Times go through a DuckDB
Python UDF that calls `times.to_utc_and_local` (both systems are America/New_York wall-clock, the new system's
`+00` suffix is ignored). A value that cannot be parsed becomes NULL and is counted by reason in `norm_issues`; no
row is dropped silently except exact duplicate IDs, which are counted too (REQ-ING-2.2). Output order is by
(id, system), so the table does not depend on input row order (REQ-ING-2.3).

`cases_norm` columns: id, system, open_time_utc, close_time_utc, open_time_local, close_time_local, target_time_utc,
local_ambiguous, local_nonexistent, on_time, status, closure_text, closure_code, type_raw, queue, department,
neighborhood, district, street, lat, lon, source, segment_id, segment_snap_m, coroner_label. Timestamps are naive
UTC (or naive Boston wall-clock for the `*_local` columns).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from undead311.ingest.text import register_text_udfs
from undead311.ingest.times import (
    LOCAL_AMBIGUOUS,
    LOCAL_NONEXISTENT,
    parse_legacy_stamp,
    parse_new_system_stamp,
    to_utc_and_local,
)

ERR = "!ERR"

NORM_COLUMNS = (
    "id", "system", "open_time_utc", "close_time_utc", "open_time_local", "close_time_local", "target_time_utc",
    "local_ambiguous", "local_nonexistent", "on_time", "status", "closure_text", "closure_code", "type_raw", "queue",
    "department", "neighborhood", "district", "street", "lat", "lon", "source", "segment_id", "segment_snap_m",
    "coroner_label",
)  # fmt: skip


def time_udf(system: str | None, text: str | None) -> str | None:
    """'utc|local|flags' for a wall-clock stamp, None for empty input, ERR for an unparseable value (REQ-ING-TZ.1-2)."""
    if text is None or not text.strip():
        return None
    try:
        wall = parse_legacy_stamp(text) if system == "legacy" else parse_new_system_stamp(text)
        if wall is None:
            return None
        utc, local, flags = to_utc_and_local(wall)
    except (ValueError, OverflowError):
        return ERR
    return f"{utc.replace(tzinfo=None).isoformat(sep=' ')}|{local.isoformat(sep=' ')}|{','.join(sorted(flags))}"


@dataclass
class NormReport:
    rows: int = 0
    issues: dict[str, int] = field(default_factory=dict)


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    return {r[0] for r in con.execute(
        "select column_name from information_schema.columns where table_name = ?", [table]).fetchall()}  # fmt: skip


def _col(cols: set[str], name: str) -> str:
    return f"nullif(trim({name}), '')" if name in cols else "NULL::VARCHAR"


def _first_col(cols: set[str], *names: str) -> str:
    """The first of `names` that the table has, else NULL. The legacy yearly files spell two columns `sla_target_dt`
    and `on_time` (a documented older header said `target_dt` and `ontime`); both spellings are read (REQ-STAT-SF.1)."""
    for name in names:
        if name in cols:
            return _col(cols, name)
    return "NULL::VARCHAR"


def normalize(con: duckdb.DuckDBPyConnection) -> NormReport:
    """Build `cases_norm` and `norm_issues` from `raw_legacy` and `raw_new` (REQ-ING-2.1-3)."""
    con.execute("select 1").fetchall()  # a half-read result from an earlier stage would block UDF registration
    try:
        con.create_function("undead_time", time_udf, ["VARCHAR", "VARCHAR"], "VARCHAR")
    except duckdb.NotImplementedException:
        pass  # already registered on this connection
    register_text_udfs(con)  # ops#214: street names arrive HTML-escaped
    lc, nc = _columns(con, "raw_legacy"), _columns(con, "raw_new")
    lg, nw = (lambda n: _col(lc, n)), (lambda n: _col(nc, n))
    con.execute("drop table if exists norm_stage")
    con.execute(f"""
        create table norm_stage as
        select {lg('case_enquiry_id')} as id, 'legacy' as system, {lg('open_dt')} as open_raw, {lg('closed_dt')} as close_raw,
               {_first_col(lc, 'sla_target_dt', 'target_dt')} as target_raw,
               {_first_col(lc, 'on_time', 'ontime')} as on_time_raw, {lg('case_status')} as status,
               {lg('closure_reason')} as closure_text, NULL::VARCHAR as closure_code, {lg('type')} as type_raw,
               {lg('queue')} as queue, {lg('department')} as department, {lg('neighborhood')} as neighborhood,
               {lg('pwd_district')} as district, undead_unescape({lg('location_street_name')}) as street,
               {lg('latitude')} as lat_raw, {lg('longitude')} as lon_raw, {lg('source')} as source,
               {lg('filename')} as filename
        from raw_legacy
        union all
        select {nw('case_id')}, 'new', {nw('open_date')}, {nw('close_date')}, {nw('target_close_date')},
               {nw('on_time')}, {nw('case_status')},
               coalesce({nw('closure_comments')}, {nw('closure_reason')}), {nw('closure_reason')}, {nw('service_name')},
               {nw('assigned_team')}, {nw('assigned_department')}, {nw('neighborhood')}, {nw('public_works_district')},
               undead_unescape({nw('street_name')}), {nw('latitude')}, {nw('longitude')}, {nw('report_source')}, {nw('filename')}
        from raw_new
    """)  # fmt: skip
    con.execute("drop table if exists norm_timed")
    con.execute("""
        create table norm_timed as
        select *, undead_time(system, open_raw) as o, undead_time(system, close_raw) as c,
               undead_time(system, target_raw) as t
        from norm_stage where id is not null
    """)
    amb, non = LOCAL_AMBIGUOUS, LOCAL_NONEXISTENT
    ok = lambda col: f"case when {col} = '{ERR}' then NULL else {col} end"
    part = lambda col, i: f"try_cast(split_part({ok(col)}, '|', {i}) as timestamp)"
    con.execute("drop table if exists cases_norm")
    con.execute(f"""
        create table cases_norm as
        select id, system,
               {part('o', 1)} as open_time_utc, {part('c', 1)} as close_time_utc,
               {part('o', 2)} as open_time_local, {part('c', 2)} as close_time_local,
               {part('t', 1)} as target_time_utc,
               (coalesce(split_part({ok('o')}, '|', 3), '') like '%{amb}%'
                or coalesce(split_part({ok('c')}, '|', 3), '') like '%{amb}%') as local_ambiguous,
               (coalesce(split_part({ok('o')}, '|', 3), '') like '%{non}%'
                or coalesce(split_part({ok('c')}, '|', 3), '') like '%{non}%') as local_nonexistent,
               case upper(on_time_raw) when 'ONTIME' then true when 'OVERDUE' then false end as on_time,
               status, closure_text, closure_code, type_raw, queue, department, neighborhood, district, street,
               try_cast(lat_raw as double) as lat, try_cast(lon_raw as double) as lon, source,
               NULL::VARCHAR as segment_id, NULL::DOUBLE as segment_snap_m, NULL::VARCHAR as coroner_label
        from (select *, row_number() over (partition by id, system order by filename, open_raw, close_raw, status, closure_text,
                                  type_raw, lat_raw, lon_raw, source, department, street) as dup_rank
              from norm_timed)
        where dup_rank = 1
        order by id, system
    """)  # fmt: skip
    issues = {
        "unparseable_open_time": f"select count(*) from norm_timed where o = '{ERR}'",
        "unparseable_close_time": f"select count(*) from norm_timed where c = '{ERR}'",
        "unparseable_target_time": f"select count(*) from norm_timed where t = '{ERR}'",
        "unparseable_coordinate": "select count(*) from norm_timed where (lat_raw is not null and try_cast(lat_raw as double) is null)"
        " or (lon_raw is not null and try_cast(lon_raw as double) is null)",
        "missing_id": "select count(*) from norm_stage where id is null",
        "duplicate_id": "select (select count(*) from norm_timed) - (select count(*) from cases_norm)",
        "closed_without_close_time": "select count(*) from cases_norm where status = 'Closed' and close_time_utc is null",
        "close_before_open": "select count(*) from cases_norm where close_time_utc < open_time_utc",
    }  # fmt: skip
    con.execute("drop table if exists norm_issues")
    con.execute("create table norm_issues(reason varchar, n bigint)")
    report = NormReport(rows=con.execute("select count(*) from cases_norm").fetchone()[0])
    for reason, sql in issues.items():
        n = con.execute(sql).fetchone()[0]
        con.execute("insert into norm_issues values (?, ?)", [reason, n])
        report.issues[reason] = n
    for t in ("norm_stage", "norm_timed"):
        con.execute(f"drop table {t}")
    return report
