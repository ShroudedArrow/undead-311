"""REQ-EXP-1.1 (ops#63): one neighborhood name per area across the legacy and new systems."""

from __future__ import annotations

import json

import duckdb
from hypothesis import given
from hypothesis import strategies as st
from test_pipeline import raw_folder

from undead311.ingest.neighborhoods import ALIASES, canonical_neighborhood, canonicalize
from undead311.pipeline import run_pipeline


def test_req_ing_nbr_1_paired_names_become_one_and_boston_is_not_a_neighborhood():
    assert canonical_neighborhood("Allston") == canonical_neighborhood("Brighton") == "Allston / Brighton"
    assert canonical_neighborhood("Mattapan") == "Greater Mattapan"
    assert canonical_neighborhood("Downtown") == "Downtown / Financial District"
    assert canonical_neighborhood("Longwood") == canonical_neighborhood("Fenway")
    assert canonical_neighborhood("South Boston") == canonical_neighborhood("South Boston Waterfront")
    assert canonical_neighborhood("Boston") is None and canonical_neighborhood("  ") is None and canonical_neighborhood(None) is None
    assert canonical_neighborhood("Roxbury") == "Roxbury"


@given(st.text(max_size=30))
def test_req_ing_nbr_1_canonicalizing_twice_changes_nothing(name):
    once = canonical_neighborhood(name)
    assert canonical_neighborhood(once) == once
    assert set(ALIASES.values()).isdisjoint(ALIASES)  # no alias chains


def test_req_ing_nbr_1_canonicalize_rewrites_the_table_and_counts_changed_rows():
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, neighborhood varchar)")
    con.executemany("insert into cases_clean values (?,?)", [("1", "Allston"), ("2", "Allston / Brighton"), ("3", "Boston"), ("4", None), ("5", "Roxbury")])
    assert canonicalize(con) == 2
    assert dict(con.execute("select id, neighborhood from cases_clean").fetchall()) == {
        "1": "Allston / Brighton", "2": "Allston / Brighton", "3": None, "4": None, "5": "Roxbury"}  # fmt: skip


def test_req_ing_nbr_1_the_export_carries_one_name_per_area(tmp_path):
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "d", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    names = {z["neighborhood"] for z in json.loads((out / "zombies.json").read_text())["zombies"]}
    assert not names & (set(ALIASES) | {"Boston"})
