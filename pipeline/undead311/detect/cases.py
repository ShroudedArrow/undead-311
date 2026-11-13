"""Build `Case` objects from DuckDB tables or the committed sample CSV.

Tolerates missing optional columns (the sample has no segment or label columns). Rows whose scope tier is not
`core` or `sensitivity`, or that have no open time or coordinates, are skipped here; `clean` already counts them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb

from undead311.detect.model import Case


def _aware(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _truthy(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() == "true")


def _nodes(value) -> tuple[tuple[str, float], ...]:
    if not value:
        return ()
    if isinstance(value, str):
        pairs = [x.split(":") for x in value.split(";") if x]
        return tuple(sorted((n, float(d)) for n, d in pairs))
    return tuple(sorted((n, float(d)) for n, d in value))


def cases_from_table(con: duckdb.DuckDBPyConnection, table: str = "cases_clean") -> list[Case]:
    """All in-scope cases of `table`, sorted by (id) so the result never depends on storage order."""
    cur = con.execute(f"select * from {table}")
    names = [d[0] for d in cur.description]
    out = []
    for row in cur.fetchall():
        r = dict(zip(names, row, strict=True))
        if r.get("scope_tier") not in ("core", "sensitivity") or r.get("open_time_utc") is None:
            continue
        if r.get("lat") is None or r.get("lon") is None:
            continue
        status = r.get("status")
        close = _aware(r.get("close_time_utc")) if status == "Closed" else None
        preds = r.get("predecessor_ids") or ""
        out.append(
            Case(
                id=r["id"],
                system=r["system"],
                open_utc=_aware(r["open_time_utc"]),
                close_utc=close,
                type_raw=r.get("type_raw") or "",
                type_family=r.get("type_family") or "",
                scope_tier=r["scope_tier"],
                city_originated_type=_truthy(r.get("city_originated_type")),
                catch_all=_truthy(r.get("catch_all")),
                predecessor_ids=tuple(x for x in preds.split(";") if x),
                source=r.get("source") or None,
                closure_text=r.get("closure_text") or None,
                closure_code=r.get("closure_code") or None,
                coroner_label=r.get("coroner_label") or None,
                status=status,
                lat=float(r["lat"]),
                lon=float(r["lon"]),
                segment_id=r.get("segment_id") or None,
                segment_snap_m=None if r.get("segment_snap_m") is None else float(r["segment_snap_m"]),
                near_nodes=_nodes(r.get("near_nodes")),
                department=r.get("department") or None,
                neighborhood=r.get("neighborhood") or None,
                district=r.get("district") or None,
                street=r.get("street") or None,
                on_time=r.get("on_time") if isinstance(r.get("on_time"), bool) else None,
            )
        )
    out.sort(key=lambda c: c.id)
    return out


def cases_from_sample_csv(path: Path) -> list[Case]:
    """Load data/sample/sample_311.csv (already crosswalked, core scope) as Cases (REQ-ING-SAMPLE)."""
    con = duckdb.connect()
    con.execute(
        "create table s as select * from read_csv(?, all_varchar=true, header=true)", [str(path)]
    )
    con.execute("""
        create table sample_cases as
        select id, system, try_cast(open_time_utc as timestamp) as open_time_utc,
               try_cast(close_time_utc as timestamp) as close_time_utc, status, closure_text,
               nullif(closure_code, '') as closure_code, type_raw, type_family, scope_tier,
               city_originated_type, predecessor_ids, department, neighborhood, street,
               try_cast(lat as double) as lat, try_cast(lon as double) as lon, source
        from s
    """)
    return cases_from_table(con, "sample_cases")
