"""Neighborhood areas and street length, for the neighborhood Poisson check and reporting intensity (REQ-STAT-NBR.2,
REQ-STAT-REP.1).

`store_neighborhood_geometry` writes the DuckDB table `neighborhood_areas(name, area_m2, street_km)`, one row per
reported neighborhood name (the legacy-style names of `neighborhoods.ALIASES`). The area is the union of the City's
polygons that fold into the name, in m2 (the equirectangular scale used by snapping). `street_km` is the length of the
SAM segments whose midpoint lies in those polygons. Without the boundaries file the table is created empty and the
statistics that need it are skipped with a status flag. Without the SAM file `street_km` is NULL.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np
import shapely
from shapely import contains_xy
from shapely.geometry import LineString
from shapely.ops import unary_union

from undead311.ingest.neighborhoods import canonical_neighborhood, load_boundaries
from undead311.ingest.snap import M_PER_DEG_LAT, M_PER_DEG_LON, load_segments

_SCALE = np.array([M_PER_DEG_LON, M_PER_DEG_LAT])


def _metres(geom):
    """The geometry in m (equirectangular, the scale snapping uses)."""
    return shapely.transform(geom, lambda xy: xy * _SCALE)


def store_neighborhood_geometry(
    con: duckdb.DuckDBPyConnection, boundaries: Path | None, segments: Path | None = None
) -> int:
    """Create `neighborhood_areas`; returns the number of rows (0 without a boundaries file)."""
    con.execute("drop table if exists neighborhood_areas")
    con.execute("create table neighborhood_areas(name varchar, area_m2 double, street_km double)")
    if boundaries is None or not Path(boundaries).is_file():
        return 0
    areas = load_boundaries(Path(boundaries))
    shapes: dict[str, list] = defaultdict(list)
    for poly_name, shape in areas:
        name = canonical_neighborhood(poly_name)
        if name:
            shapes[name].append(shape)
    km: dict[str, float] | None = None
    if segments is not None and Path(segments).is_file():
        km = dict.fromkeys(shapes, 0.0)
        segs = load_segments(Path(segments))
        if segs:
            mids = np.array([LineString(s.coords).interpolate(0.5, normalized=True).coords[0] for s in segs])
            lengths = np.array([_metres(LineString(s.coords)).length for s in segs])
            owner = np.full(len(segs), None, dtype=object)
            for poly_name, shape in areas:  # the first polygon by name owns a point on an overlap, as for cases
                hit = (owner == None) & contains_xy(shape, mids[:, 0], mids[:, 1])
                owner[hit] = poly_name
            for poly_name, length in zip(owner, lengths, strict=True):
                name = canonical_neighborhood(poly_name) if poly_name is not None else None
                if name:
                    km[name] += float(length) / 1000.0
    rows = [
        (name, float(_metres(unary_union(parts)).area), None if km is None else km[name])
        for name, parts in sorted(shapes.items())
    ]
    con.executemany("insert into neighborhood_areas values (?,?,?)", rows)
    return len(rows)
