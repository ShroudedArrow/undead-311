"""Cleaning and exclusions (REQ-ING-CLEAN, ZD step 1).

`clean` splits `cases_x` into `cases_clean` (in scope, usable) and `cases_excluded(id, system, type_family, reason)`.
Each excluded case gets exactly one reason, tested in this order:
`unlisted_type`, `excluded_type`, `null_coords`, `out_of_bounds`, `placeholder`, `null_open_time`.
Every exclusion is counted by reason, family and system; nothing is dropped silently (REQ-ING-CLEAN.2-3).
Candidate placeholder points (one rounded coordinate shared by more than 200 cases) are reported, not dropped
(REQ-ING-CLEAN.4); the owner decides whether to add them to ZD step 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

# Boston bounding box (REQ-ING-CLEAN.1; same box as pipeline/scripts/build_sample.py)
LAT_MIN, LAT_MAX = 42.2, 42.45
LON_MIN, LON_MAX = -71.2, -70.9
#: The two real placeholder points of ZD step 1, compared after rounding to 4 decimals.
PLACEHOLDER_POINTS = ((42.3603, -71.0583), (42.3595, -71.0588))
PLACEHOLDER_CANDIDATE_MIN = 200
REASONS = ("unlisted_type", "excluded_type", "null_coords", "out_of_bounds", "placeholder", "null_open_time")


@dataclass
class Exclusions:
    counts: dict[str, int] = field(default_factory=dict)
    by_family_system: list[dict] = field(default_factory=list)
    candidate_placeholders: list[dict] = field(default_factory=list)
    kept: int = 0


def ids_by_reason(con: duckdb.DuckDBPyConnection, reasons: tuple[str, ...] = REASONS) -> dict[str, list[str]]:
    """Excluded case IDs by reason, sorted (REQ-ING-CLEAN.2)."""
    out: dict[str, list[str]] = {r: [] for r in reasons}
    for reason, cid in con.execute("select reason, id from cases_excluded order by reason, id").fetchall():
        if reason in out:
            out[reason].append(cid)
    return out


def clean(con: duckdb.DuckDBPyConnection) -> Exclusions:
    """Create `cases_clean` and `cases_excluded` from `cases_x` (REQ-ING-CLEAN.1-4)."""
    placeholder = " or ".join(f"(round(lat, 4) = {a} and round(lon, 4) = {b})" for a, b in PLACEHOLDER_POINTS)
    con.execute("drop table if exists cases_reason")
    con.execute(f"""
        create table cases_reason as
        select *, case
            when scope_tier is null then 'unlisted_type'
            when scope_tier = 'excluded' then 'excluded_type'
            when lat is null or lon is null then 'null_coords'
            when lat not between {LAT_MIN} and {LAT_MAX} or lon not between {LON_MIN} and {LON_MAX} then 'out_of_bounds'
            when {placeholder} then 'placeholder'
            when open_time_utc is null then 'null_open_time'
        end as reason
        from cases_x
    """)
    con.execute("drop table if exists cases_excluded")
    con.execute(
        "create table cases_excluded as select id, system, type_family, type_raw, reason from cases_reason "
        "where reason is not null order by reason, id, system"
    )
    con.execute("drop table if exists cases_clean")
    con.execute("create table cases_clean as select * exclude (reason) from cases_reason where reason is null order by id, system")
    report = Exclusions()
    report.counts = {r: 0 for r in REASONS}
    report.counts.update(dict(con.execute("select reason, count(*) from cases_excluded group by 1").fetchall()))
    report.by_family_system = [
        {"reason": r, "type_family": f, "system": s, "n": n}
        for r, f, s, n in con.execute(
            "select reason, coalesce(type_family, 'unlisted'), system, count(*) from cases_excluded "
            "group by all order by all"
        ).fetchall()
    ]
    report.kept = con.execute("select count(*) from cases_clean").fetchone()[0]
    report.candidate_placeholders = [
        {"lat": lat, "lon": lon, "n": n}
        for lat, lon, n in con.execute(
            f"select round(lat, 4), round(lon, 4), count(*) as n from cases_clean "
            f"group by 1, 2 having count(*) > {PLACEHOLDER_CANDIDATE_MIN} order by n desc, 1, 2"
        ).fetchall()
    ]
    con.execute("drop table cases_reason")
    return report
