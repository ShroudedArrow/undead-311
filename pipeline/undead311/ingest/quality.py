"""Data-quality checks that turn a silent gap into a status anomaly (REQ-STAT-SF.1, ops#49).

`normalize._col` returns NULL for a column the raw file does not have, which is how legacy `on_time` was null in every
full run without any alert. `on_time_anomalies` flags a system whose closed in-scope cases mostly have no on-time value.
"""

from __future__ import annotations

import duckdb

ON_TIME_MIN_KNOWN_SHARE = 0.9  # a system below this share of known on_time values among closed cases is an anomaly


def on_time_coverage(con: duckdb.DuckDBPyConnection, table: str = "cases_clean") -> dict[str, tuple[int, int]]:
    """`{system: (closed cases with a known on_time, closed in-scope cases)}` (REQ-STAT-SF.1)."""
    rows = con.execute(f"""
        select system, count(*) filter (where on_time is not null), count(*)
        from {table}
        where status = 'Closed' and close_time_utc is not null and scope_tier in ('core', 'sensitivity')
        group by system order by system
    """).fetchall()  # fmt: skip
    return {s: (int(k), int(n)) for s, k, n in rows}


def on_time_anomalies(coverage: dict[str, tuple[int, int]], minimum: float = ON_TIME_MIN_KNOWN_SHARE) -> list[str]:
    """One anomaly line per system whose known-on_time share of closed in-scope cases is below `minimum`."""
    out = []
    for system, (known, closed) in sorted(coverage.items()):
        if closed and known / closed < minimum:
            out.append(
                f"on_time is known for {known} of {closed} closed in-scope {system}-system cases ({known / closed:.0%}, "
                f"below {minimum:.0%}); check the raw on_time column (REQ-STAT-SF.1)"
            )
    return out
