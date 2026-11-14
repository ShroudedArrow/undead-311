"""One neighborhood name per area across the two systems (REQ-EXP-1.1, ops#63).

The legacy system and the new system name some areas differently: Allston and Brighton are one area ("Allston /
Brighton") in the new system, and so are Downtown, Mattapan, Fenway with Longwood, and South Boston with its Waterfront.
"Boston" is the city, not a neighborhood: such a case carries no neighborhood and stays out of neighborhood rankings.
Without this the map filter splits one area into two options and a ranking counts it twice at half strength.
"""

from __future__ import annotations

import duckdb

_FENWAY = "Fenway / Kenmore / Audubon Circle / Longwood"
_SOUTHIE = "South Boston / South Boston Waterfront"

ALIASES: dict[str, str] = {
    "Allston": "Allston / Brighton",
    "Brighton": "Allston / Brighton",
    "Downtown": "Downtown / Financial District",
    "Mattapan": "Greater Mattapan",
    "Fenway": _FENWAY,
    "Longwood": _FENWAY,
    "South Boston": _SOUTHIE,
    "South Boston Waterfront": _SOUTHIE,
}
NOT_A_NEIGHBORHOOD = frozenset({"Boston"})


def canonical_neighborhood(name: str | None) -> str | None:
    """The one name for an area, or None when the value is empty or is the city itself."""
    if name is None or not name.strip() or name.strip() in NOT_A_NEIGHBORHOOD:
        return None
    name = name.strip()
    return ALIASES.get(name, name)


def canonicalize(con: duckdb.DuckDBPyConnection, table: str = "cases_clean") -> int:
    """Rewrite `neighborhood` on `table`; returns the number of rows whose value changed."""
    changed = 0
    for (name,) in con.execute(f"select distinct neighborhood from {table} where neighborhood is not null").fetchall():
        new = canonical_neighborhood(name)
        if new != name:
            changed += con.execute(f"select count(*) from {table} where neighborhood = ?", [name]).fetchone()[0]
            con.execute(f"update {table} set neighborhood = ? where neighborhood = ?", [new, name])
    return changed
