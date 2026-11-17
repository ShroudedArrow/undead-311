"""Department crosswalk (REQ-ING-DEPT): one department key across both systems.

The legacy system writes a code (`PWDx`) and the new system a name (`Public Works Department (PWD)`), so a department was two
rows in every table. `department_crosswalk.csv` maps each raw value to one key (the legacy code, which the site already uses),
with the source of every mapping. `status` is `official` (the CRM Value Code Index lists the code), `mapped` (a name or
abbreviation match, source named in the row) or `flagged` (no mapping found: the value is kept under its own name and the
owner decides). Two more statuses record owner decisions (2026-11-16): `as_published` (kept as the code the city
publishes, shown with that note) and `excluded` (a test queue: `clean` drops its cases as `test_data`). A value that is missing from the file is also kept as it is and counted as unlisted. A missing (NULL)
department stays NULL.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

DEPARTMENTS_CSV = Path(__file__).with_name("department_crosswalk.csv")
STATUSES = ("official", "mapped", "as_published", "excluded", "flagged")


@dataclass
class DepartmentReport:
    flagged: dict[str, int] = field(default_factory=dict)  # "<system>:<raw>" -> cases kept under their own value
    unlisted: dict[str, int] = field(default_factory=dict)  # values not in the file at all
    missing: int = 0  # cases with no department


def read_departments(path: Path = DEPARTMENTS_CSV) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r["status"] not in STATUSES:
            raise ValueError(f"department_crosswalk.csv: status {r['status']!r} is not one of {STATUSES}")
        if not r["source"].strip():
            raise ValueError(f"department_crosswalk.csv: {r['system']}/{r['department_raw']} has no source")
    return rows


def has_department(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    """A table without a `department` column (a unit-test table) has nothing to map."""
    return any(r[0] == "department" for r in con.execute(f"describe {table}").fetchall())


def apply_departments(con: duckdb.DuckDBPyConnection, table: str, path: Path = DEPARTMENTS_CSV) -> DepartmentReport:
    """Replace `department` in `table` by its mapped key (REQ-ING-DEPT.1) and report what could not be mapped."""
    rows = read_departments(path)
    if not has_department(con, table):
        return DepartmentReport()
    con.execute("create or replace temp table dept_map(system varchar, raw varchar, dept varchar, status varchar)")
    con.executemany("insert into dept_map values (?,?,?,?)", [(r["system"], r["department_raw"], r["department"], r["status"]) for r in rows])
    report = DepartmentReport()
    for system, raw, status, n in con.execute(
        f"select t.system, t.department, m.status, count(*) from {table} t "
        "left join dept_map m on m.system = t.system and m.raw = t.department group by all"
    ).fetchall():
        if raw is None:
            report.missing += n
        elif status is None:
            report.unlisted[f"{system}:{raw}"] = n
        elif status == "flagged":
            report.flagged[f"{system}:{raw}"] = n
    con.execute(
        f"update {table} t set department = m.dept from dept_map m where m.system = t.system and m.raw = t.department"
    )
    con.execute("drop table dept_map")
    return report


def department_report(con: duckdb.DuckDBPyConnection, table: str, path: Path = DEPARTMENTS_CSV) -> DepartmentReport:
    """What is still unmapped in `table` after `apply_departments` (read only): flagged keys keep their own value, so they are
    found by value; a value that no row of the file produces is `unlisted`."""
    rows = read_departments(path)
    if not has_department(con, table):
        return DepartmentReport()
    produced = {(r["system"], r["department"]) for r in rows}
    flagged = {(r["system"], r["department"]) for r in rows if r["status"] == "flagged"}
    report = DepartmentReport()
    for system, dept, n in con.execute(f"select system, department, count(*) from {table} group by all").fetchall():
        if dept is None:
            report.missing += n
        elif (system, dept) in flagged:
            report.flagged[f"{system}:{dept}"] = n
        elif (system, dept) not in produced:
            report.unlisted[f"{system}:{dept}"] = n
    return report
