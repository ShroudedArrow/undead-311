"""REQ-ING-2.1 (ops#63, ops#91): one neighborhood name per area across the legacy and new systems."""

from __future__ import annotations

import json

import duckdb
from hypothesis import given
from hypothesis import strategies as st
from test_pipeline import raw_folder

from undead311.ingest.neighborhoods import ALIASES, canonical_neighborhood, canonicalize
from undead311.pipeline import run_pipeline


def test_req_ing_2_1_nbr_paired_names_become_one_and_boston_is_not_a_neighborhood():
    assert canonical_neighborhood("Allston") == canonical_neighborhood("Brighton") == "Allston / Brighton"
    assert canonical_neighborhood("Mattapan") == "Greater Mattapan"
    assert canonical_neighborhood("Downtown") == "Downtown / Financial District"
    assert canonical_neighborhood("Longwood") == canonical_neighborhood("Fenway")
    assert canonical_neighborhood("South Boston") == canonical_neighborhood("South Boston Waterfront")
    assert canonical_neighborhood("Boston") is None and canonical_neighborhood("  ") is None and canonical_neighborhood(None) is None
    assert canonical_neighborhood("Roxbury") == "Roxbury"


def test_req_ing_2_1_nbr_areas_with_no_legacy_name_fold_into_their_legacy_parent():
    """ops#91: the five new-system areas the legacy system never names no longer stay split by system."""
    for name in ("North End", "West End", "Chinatown", "Leather District", "Downtown"):
        assert canonical_neighborhood(name) == "Downtown / Financial District"
    assert canonical_neighborhood("Bay Village") == "Back Bay"


@given(st.text(max_size=30))
def test_req_ing_2_1_nbr_canonicalizing_twice_changes_nothing(name):
    once = canonical_neighborhood(name)
    assert canonical_neighborhood(once) == once
    assert set(ALIASES.values()).isdisjoint(ALIASES)  # no alias chains


def test_req_ing_2_1_nbr_canonicalize_rewrites_the_table_and_counts_changed_rows():
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, neighborhood varchar, lat double, lon double)")
    names = [("1", "Allston"), ("2", "Allston / Brighton"), ("3", "Boston"), ("4", None), ("5", "Roxbury")]
    con.executemany("insert into cases_clean values (?,'legacy',?,null,null)", names)
    assert canonicalize(con) == 2
    assert dict(con.execute("select id, neighborhood from cases_clean").fetchall()) == {
        "1": "Allston / Brighton", "2": "Allston / Brighton", "3": None, "4": None, "5": "Roxbury"}  # fmt: skip


def test_req_ing_2_1_nbr_the_export_carries_one_name_per_area(tmp_path):
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "d", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    names = {z["neighborhood"] for z in json.loads((out / "zombies.json").read_text())["zombies"]}
    assert not names & (set(ALIASES) | {"Boston"})


def _boundaries(tmp_path):
    """Two unit squares (Fenway and Allston overlap on purpose, as in the City's file) and a Downtown square."""
    def square(name, x0, y0, x1, y1):
        ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
        return {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [ring]}}

    feats = [square("Fenway", 0, 0, 2, 2), square("Allston", 1, 0, 3, 2), square("North End", 10, 10, 11, 11)]
    path = tmp_path / "neighborhood_boundaries.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_req_ing_2_1_nbr_point_in_polygon_names_both_systems_alike(tmp_path):
    """ops#91: legacy 'Boston' gets its area, and a legacy and a new case at one point get one name."""
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, neighborhood varchar, lat double, lon double)")
    rows = [
        ("1", "legacy", "Boston", 10.5, 10.5), ("2", "new", "North End", 10.6, 10.6), ("3", "legacy", "Allston", 0.5, 0.5),
        ("4", "new", "Allston", 0.5, 2.5), ("5", "legacy", "Boston", 50.0, 50.0), ("6", "new", None, None, None),
        ("7", "legacy", "Back Bay", 50.0, 50.0), ("8", "legacy", "Boston", 0.5, 1.5),
    ]  # fmt: skip
    con.executemany("insert into cases_clean values (?,?,?,?,?)", rows)
    changed = canonicalize(con, boundaries=_boundaries(tmp_path))
    got = dict(con.execute("select id, neighborhood from cases_clean").fetchall())
    assert got["1"] == got["2"] == "Downtown / Financial District"
    assert got["3"] == "Fenway / Kenmore / Audubon Circle / Longwood"  # point lies in the overlap of Fenway and Allston: name order
    assert got["4"] == "Allston / Brighton"
    assert got["5"] is None and got["7"] == "Back Bay"  # outside every polygon: the case's own name, folded; "Boston" is none
    assert got["6"] is None and got["8"] is not None
    assert changed == 6


def test_req_ing_2_1_nbr_overlap_goes_to_the_first_name_whatever_the_file_order(tmp_path):
    path = _boundaries(tmp_path)
    data = json.loads(path.read_text())
    data["features"].reverse()
    other = tmp_path / "reversed.geojson"
    other.write_text(json.dumps(data))
    for p in (path, other):
        con = duckdb.connect()
        con.execute("create table cases_clean(id varchar, system varchar, neighborhood varchar, lat double, lon double)")
        con.execute("insert into cases_clean values ('1','new','Boston',0.5,1.5)")
        canonicalize(con, boundaries=p)
        assert con.execute("select neighborhood from cases_clean").fetchone()[0].startswith("Allston")


def test_req_ing_2_1_nbr_no_name_in_the_sample_belongs_to_one_system_only():
    """ops#91: with no boundaries file, folding each case's own name still leaves one name set for both systems."""
    import csv
    from pathlib import Path

    sample = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample_311.csv"
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, neighborhood varchar, lat double, lon double)")
    rows = list(csv.DictReader(sample.open()))
    con.executemany("insert into cases_clean values (?,?,?,null,null)", [(r["id"], r["system"], r["neighborhood"] or None) for r in rows])
    canonicalize(con)
    by_system = {s: {n for (n,) in con.execute("select distinct neighborhood from cases_clean where system = ? and neighborhood is not null", [s]).fetchall()} for s in ("legacy", "new")}  # fmt: skip
    assert by_system["legacy"] and by_system["legacy"] == by_system["new"]


def test_req_ing_2_1_nbr_the_run_reads_boundaries_from_raw_and_warns_when_they_are_missing(tmp_path):
    raw, snap = raw_folder(tmp_path)
    kw = {"raw_dir": raw, "snapshot_md": snap, "run_time": "2026-11-13T00:00:00Z"}
    plain = run_pipeline(out_dir=tmp_path / "o1", work_dir=tmp_path / "d1", **kw)
    assert any("neighborhood boundaries unavailable" in w for w in plain.warnings)
    ring = [[-71.2, 42.2], [-71.0, 42.2], [-71.0, 42.3], [-71.2, 42.3], [-71.2, 42.2]]
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Roxbury"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}  # fmt: skip
    (raw / "neighborhood_boundaries.geojson").write_text(json.dumps(geo))
    full = run_pipeline(out_dir=tmp_path / "o2", work_dir=tmp_path / "d2", **kw)
    assert not any("neighborhood boundaries unavailable" in w for w in full.warnings)
    names = {z["neighborhood"] for z in json.loads((tmp_path / "o2" / "zombies.json").read_text())["zombies"]}
    assert names == {"Roxbury"}  # the files said Dorchester; the point lies in the Roxbury polygon
