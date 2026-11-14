"""One neighborhood name per area across the two systems (REQ-ING-NBR.1, ops#63, ops#91).

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
import pandas as pd
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
    """The polygon name containing each point (REQ-ING-NBR.1, ops#91), or None; the first polygon by name wins."""
    out = np.full(len(lat), None, dtype=object)
    for name, poly in areas:
        hit = pd.isna(out) & contains_xy(poly, lon, lat)  # one numpy mask per polygon (ops#97)
        out[hit] = name
    return out


def _folded(values: pd.Series) -> np.ndarray:
    """`canonical_neighborhood` of every value, computed once per distinct value."""
    names = {v: canonical_neighborhood(v) for v in values.dropna().unique()}
    return values.map(names).astype(object).where(values.notna(), None).to_numpy()


def canonicalize(con: duckdb.DuckDBPyConnection, table: str = "cases_clean", boundaries: Path | None = None) -> int:
    """Rewrite `neighborhood` on `table`; returns the number of rows whose value changed (REQ-ING-NBR.1).

    With a boundaries file, every row with a point is named by point in polygon (the same rule for both systems);
    other rows, or all rows when there is no file, keep their own name folded through `ALIASES`. The new names are
    computed with numpy masks and written back with one `update ... from` join (ops#97)."""
    areas = load_boundaries(boundaries) if boundaries is not None and boundaries.is_file() else []
    df = con.execute(f"select id, system, neighborhood, lat, lon from {table}").df()
    if df.empty:
        return 0
    old = df["neighborhood"].astype(object).where(df["neighborhood"].notna(), None).to_numpy()
    new = _folded(df["neighborhood"])
    if areas:
        found = area_names(areas, df["lat"].to_numpy(dtype=float), df["lon"].to_numpy(dtype=float))
        polygon = pd.Series(found, dtype=object)
        by_polygon = _folded(polygon)
        new = np.where(pd.notna(found), by_polygon, new)
    changed = pd.notna(new) != pd.notna(old)
    both = pd.notna(new) & pd.notna(old)
    changed = changed | (both & (new != old))
    if changed.any():
        changes = pd.DataFrame({"id": df["id"][changed], "system": df["system"][changed], "nbr": new[changed]})
        con.register("nbr_new", changes)
        con.execute(f"update {table} t set neighborhood = r.nbr from nbr_new r where t.id = r.id and t.system = r.system")
        con.unregister("nbr_new")
    return int(changed.sum())
