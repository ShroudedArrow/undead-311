"""One neighborhood name per area across the two systems (REQ-ING-2.1, ops#63, ops#91).

The legacy system reports 17 coarse names and the new system 26 finer ones (the City's neighborhood boundaries).
Both systems are reported under the legacy-style names, so an area has one name whichever system a case came from.

A case with a valid point gets its name from the boundaries file (`neighborhood_boundaries.geojson`, point in
polygon), the same rule for both systems. The polygon name is then folded to the reported name by `ALIASES`. The
fold is data-checked: each new-system area with no legacy name of its own goes to the legacy name that holds the
legacy cases inside its polygon (North End, Chinatown, Leather District and West End to Downtown / Financial
District, 276/276, 70/71, 33/33 and 50/80 of the sample's legacy cases; Bay Village to Back Bay, 67/71). Legacy
"Boston" is the city, not a neighborhood, so the boundaries file gives those cases an area. A point inside no polygon,
or a run with no boundaries file, falls back to the case's own name run through `ALIASES` (still one name per area);
a name that is not an area ("Boston", empty) leaves the case without a neighborhood, out of neighborhood rankings.
Without this the map filter splits one area into two options and a ranking counts it twice at half strength.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
from shapely import contains_xy
from shapely.geometry import shape

BOUNDARIES_FILE = "neighborhood_boundaries.geojson"
_DOWNTOWN = "Downtown / Financial District"
_FENWAY = "Fenway / Kenmore / Audubon Circle / Longwood"
_SOUTHIE = "South Boston / South Boston Waterfront"

ALIASES: dict[str, str] = {
    "Allston": "Allston / Brighton",
    "Brighton": "Allston / Brighton",
    "Downtown": _DOWNTOWN,
    "North End": _DOWNTOWN,
    "West End": _DOWNTOWN,
    "Chinatown": _DOWNTOWN,
    "Leather District": _DOWNTOWN,
    "Bay Village": "Back Bay",
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


def load_boundaries(path: Path) -> list[tuple[str, object]]:
    """(polygon name, shape) from the boundaries GeoJSON, sorted by name so a point on a shared edge or in an
    overlap (Fenway and Allston overlap in the City's file) always gets the same area, whatever the file order."""
    feats = json.loads(path.read_text())["features"]
    return sorted(((f["properties"]["name"], shape(f["geometry"])) for f in feats), key=lambda t: t[0])


def area_names(areas: list[tuple[str, object]], lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """The polygon name containing each point (REQ-ING-2.1, ops#91), or None; the first polygon by name wins."""
    out = np.full(len(lat), None, dtype=object)
    for name, poly in areas:
        todo = np.array([o is None for o in out], dtype=bool)
        hit = todo & contains_xy(poly, lon, lat)
        out[hit] = name
    return out


def canonicalize(con: duckdb.DuckDBPyConnection, table: str = "cases_clean", boundaries: Path | None = None) -> int:
    """Rewrite `neighborhood` on `table`; returns the number of rows whose value changed (REQ-ING-2.1).

    With a boundaries file, every row with a point is named by point in polygon (the same rule for both systems);
    other rows, or all rows when there is no file, keep their own name folded through `ALIASES`."""
    areas = load_boundaries(boundaries) if boundaries is not None and boundaries.is_file() else []
    rows = con.execute(f"select id, system, neighborhood, lat, lon from {table}").fetchall()
    changes: list[tuple[str | None, str, str]] = []
    if areas:
        lat = np.array([r[3] if r[3] is not None else np.nan for r in rows], dtype=float)
        lon = np.array([r[4] if r[4] is not None else np.nan for r in rows], dtype=float)
        found = area_names(areas, lat, lon)
    for i, (cid, system, name, _la, _lo) in enumerate(rows):
        polygon = found[i] if areas else None
        new = canonical_neighborhood(polygon) if polygon is not None else canonical_neighborhood(name)
        if new != name:
            changes.append((new, cid, system))
    if changes:
        con.execute("create temp table nbr_new(nbr varchar, id varchar, system varchar)")
        con.executemany("insert into nbr_new values (?,?,?)", changes)
        con.execute(f"update {table} t set neighborhood = r.nbr from nbr_new r where t.id = r.id and t.system = r.system")
        con.execute("drop table nbr_new")
    return len(changes)
