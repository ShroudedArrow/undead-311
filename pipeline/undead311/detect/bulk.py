"""Bulk-closure detector (REQ-BULK.1-2, ZD step 10). Flag only: it never touches the Coroner label.

A (department, close date, template) group is a bulk closure when it has at least `BULK_MIN_CASES` closed in-scope cases
AND at least `BULK_RATIO` times the usual daily count of that department and template. The usual daily count is the
median daily closure count of the department and template over the days that have closures. The close date is the
Boston local date (America/New_York) of the closure; the template is the masked closure text (`mask_template`), the key
the Coroner labels use. `bulk_closure` is set on `cases_clean` for every case in a flagged group; it lowers the
confidence score and shows on the card (REQ-CONF.1), and it is separate from `coroner_label`, which ZD step 6 reads.
A case with empty closure text (nothing left after masking) is grouped by its closure code instead of its template
(`code:<closure_code>`; ZD step 10, owner decision ops#90), so the empty texts of one department do not share one template.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import duckdb

from undead311.coroner.templates import mask_template
from undead311.detect.params import DEFAULT, Params

UNKNOWN_DEPARTMENT = "(unknown)"
LOCAL_TZ = "America/New_York"


@dataclass(frozen=True)
class BulkGroup:
    department: str
    close_date: str  # YYYY-MM-DD, Boston local date
    template: str
    n_cases: int
    usual_daily: float
    ratio: float

    def to_json(self) -> dict:
        return {
            "department": self.department, "close_date": self.close_date, "template": self.template,
            "n_cases": self.n_cases, "usual_daily": round(self.usual_daily, 3), "ratio": round(self.ratio, 3),
        }  # fmt: skip


@lru_cache(maxsize=200_000)
def _template(text: str | None, code: str | None = None) -> str:
    """The grouping key: the masked closure text, or `code:<closure_code>` when the text is empty (REQ-BULK.1, ops#90)."""
    return mask_template(text) or f"code:{(code or '').strip()}"


def _load_input(con: duckdb.DuckDBPyConnection, table: str) -> None:
    has_code = con.execute(
        "select count(*) from information_schema.columns where table_name = ? and column_name = 'closure_code'", [table]
    ).fetchone()[0]  # fmt: skip
    code = "closure_code::varchar" if has_code else "NULL::varchar"
    rows = con.execute(f"""
        select id, system, coalesce(nullif(trim(department), ''), '{UNKNOWN_DEPARTMENT}'),
               cast((close_time_utc at time zone 'UTC') at time zone '{LOCAL_TZ}' as date)::varchar, closure_text, {code}
        from {table}
        where status = 'Closed' and close_time_utc is not null and scope_tier in ('core', 'sensitivity')
    """).fetchall()  # fmt: skip
    con.execute("drop table if exists bulk_input")
    con.execute("create temp table bulk_input(id varchar, system varchar, dept varchar, day varchar, template varchar)")
    if rows:
        con.executemany("insert into bulk_input values (?,?,?,?,?)", [(i, s, d, day, _template(t, c)) for i, s, d, day, t, c in rows])


def bulk_closures(con: duckdb.DuckDBPyConnection, p: Params = DEFAULT, table: str = "cases_clean") -> list[BulkGroup]:
    """All bulk-closure groups, sorted by (close date, department, template) (REQ-BULK.1)."""
    _load_input(con, table)
    rows = con.execute(f"""
        with daily as (select dept, template, day, count(*) as n from bulk_input group by all),
             usual as (select dept, template, median(n) as usual from daily group by all)
        select d.dept, d.day, d.template, d.n, u.usual, d.n / u.usual
        from daily d join usual u using (dept, template)
        where d.n >= {int(p.BULK_MIN_CASES)} and d.n >= {float(p.BULK_RATIO)} * u.usual
        order by d.day, d.dept, d.template
    """).fetchall()  # fmt: skip
    return [BulkGroup(d, day, t, int(n), float(u), float(r)) for d, day, t, n, u, r in rows]


def flag_cases(con: duckdb.DuckDBPyConnection, groups: list[BulkGroup], table: str = "cases_clean") -> int:
    """Set `bulk_closure` on `table` (true for a case in a flagged group, false otherwise); returns the flagged count.

    The Coroner label column is never written (REQ-BULK.2)."""
    con.execute(f"alter table {table} add column if not exists bulk_closure boolean")
    con.execute(f"update {table} set bulk_closure = false")
    if not groups:
        return 0
    con.execute("drop table if exists bulk_groups")
    con.execute("create temp table bulk_groups(dept varchar, day varchar, template varchar)")
    con.executemany("insert into bulk_groups values (?,?,?)", [(g.department, g.close_date, g.template) for g in groups])
    con.execute(f"""
        update {table} t set bulk_closure = true
        from bulk_input i join bulk_groups g on g.dept = i.dept and g.day = i.day and g.template = i.template
        where t.id = i.id and t.system = i.system
    """)  # fmt: skip
    return con.execute(f"select count(*) from {table} where bulk_closure").fetchone()[0]
