"""REQ-SENS-RUN.1-2: the 18 grid points plus the run without Street Light Other, stored in `grid_runs`."""

from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

import duckdb
from helpers import examples, mk
from hypothesis import given, settings
from hypothesis import strategies as st

from undead311.detect.cases import cases_from_sample_csv
from undead311.detect.core import detect
from undead311.detect.edges import sql_edges
from undead311.detect.grid import (
    GRID_MATCHING,
    GRID_RADIUS_M,
    GRID_WINDOW_DAYS,
    edges_for_window,
    grid_points,
    run_grid,
    run_id,
    store_grid,
)
from undead311.detect.params import DEFAULT

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample_311.csv"


def small_town():
    """Resurrections at several distances and gaps, so the grid points disagree, plus a Street Light Other catch-all."""
    cs = [
        mk("A1", 0, 2, x=0), mk("A2", 5, None, x=10),       # a re-report 10 m away, 3 days after closure
        mk("B1", 0, 2, x=200), mk("B2", 40, None, x=225),   # 25 m away, 38 days after
        mk("C1", 0, 2, x=400), mk("C2", 80, None, x=440),   # 40 m away, 78 days after
        mk("D1", 0, 2, x=600, family="streetlight"), mk("D2", 6, None, x=605, family="streetlight"),
    ]  # fmt: skip
    slo = mk("E1", 0, 2, x=800, family="streetlight", system="new")
    slo2 = mk("E2", 8, None, x=804, family="streetlight", system="new")
    return cs + [replace(slo, type_raw="Street Light Other"), replace(slo2, type_raw="Street Light Other")]


def test_req_sens_run_1_the_grid_is_the_18_points_of_the_definition():
    pts = grid_points()
    assert len(pts) == 18 and len({run_id(p) for p in pts}) == 18
    assert {p.matching for p in pts} == set(GRID_MATCHING) and {p.RADIUS_M for p in pts} == set(GRID_RADIUS_M)
    assert {p.WINDOW_DAYS for p in pts} == set(GRID_WINDOW_DAYS)
    assert DEFAULT in pts  # the headline run is one of the grid points
    assert all(replace(p, matching="segment", RADIUS_M=30, WINDOW_DAYS=60) == DEFAULT for p in pts if p == DEFAULT)


def test_req_sens_run_1_and_2_nineteen_runs_each_equal_to_a_direct_detector_run():
    con = duckdb.connect()
    cases = small_town()
    runs = run_grid(con, cases)
    assert len(runs) == 19 and len({r.run_id for r in runs}) == 19
    for r in runs[:18]:
        p = replace(DEFAULT, matching=r.matching, RADIUS_M=r.radius_m, WINDOW_DAYS=r.window_days)
        direct = detect(cases, p, sql_edges(con, cases, p))
        assert sum(n for *_, n in r.counts) == len(direct.zombies)
        assert r.total("headline") == direct.count("headline")
    # the grid points actually differ: the 40 m and 78-day re-reports drop out of the narrow and short points
    by = {r.run_id: r.total("headline") for r in runs}
    assert by["radius-r15-w30"] < by["radius-r50-w90"]


def test_req_sens_run_2_the_extra_run_drops_street_light_other_at_default_parameters():
    con = duckdb.connect()
    cases = small_town()
    runs = run_grid(con, cases)
    default = next(r for r in runs if r.run_id == run_id(DEFAULT))
    extra = runs[-1]
    assert extra.without_street_light_other and extra.run_id.endswith("-no-street-light-other")
    assert (extra.matching, extra.radius_m, extra.window_days) == (DEFAULT.matching, DEFAULT.RADIUS_M, DEFAULT.WINDOW_DAYS)
    assert extra.n_cases == len(cases) - 2
    assert sum(n for *_, n in default.counts) == sum(n for *_, n in extra.counts) + 1  # the E1-E2 zombie is gone
    assert not any(r.without_street_light_other for r in runs[:18])


def test_req_sens_run_1_filtered_wide_edges_equal_edges_built_at_that_window():
    """The speed-up (edges built once at the widest window, then filtered) never changes the edge set."""
    cases = cases_from_sample_csv(SAMPLE) + small_town()
    by_id = {c.id: c for c in cases}
    con = duckdb.connect()
    for matching in GRID_MATCHING:
        for radius in GRID_RADIUS_M:
            wide = sql_edges(con, cases, replace(DEFAULT, matching=matching, RADIUS_M=radius, WINDOW_DAYS=90))
            for window in GRID_WINDOW_DAYS:
                p = replace(DEFAULT, matching=matching, RADIUS_M=radius, WINDOW_DAYS=window)
                assert edges_for_window(wide, by_id, p) == sql_edges(con, cases, p)


def test_req_sens_run_1_the_tables_hold_counts_by_tier_family_and_department_and_a_run_without_zombies():
    con = duckdb.connect()
    cases = [replace(c, department="PWD") for c in small_town()[:6]] + [mk("Z", 0, None, x=5000)]
    runs = run_grid(con, cases)
    store_grid(con, runs)
    assert con.execute("select count(*) from grid_run_index").fetchone()[0] == 19
    assert con.execute("select count(distinct run_id) from grid_runs").fetchone()[0] <= 19
    tiers = {t for (t,) in con.execute("select distinct tier from grid_runs").fetchall()}
    assert tiers <= {"headline", "source_unknown", "sensitivity"} and "headline" in tiers
    dept = con.execute("select distinct department from grid_runs").fetchall()
    assert dept == [("PWD",)]
    idx = dict(con.execute("select run_id, headline from grid_run_index").fetchall())
    sums = dict(con.execute("select run_id, sum(zombies) from grid_runs where tier = 'headline' group by 1").fetchall())
    assert all(idx[r] == sums.get(r, 0) for r in idx)
    store_grid(con, runs)  # idempotent: tables are rebuilt, not appended
    assert con.execute("select count(*) from grid_run_index").fetchone()[0] == 19


def test_req_sens_run_1_empty_and_tiny_inputs_run():
    con = duckdb.connect()
    for cases in ([], [mk("only", 0, 2)]):
        runs = run_grid(con, cases)
        assert len(runs) == 19 and all(not r.counts for r in runs)
        store_grid(con, runs)
        assert con.execute("select count(*) from grid_runs").fetchone()[0] == 0


@settings(deadline=None, max_examples=examples(15))
@given(st.integers(0, 10_000))
def test_req_sens_run_1_grid_runs_do_not_depend_on_input_order(seed):
    cases = small_town()
    shuffled = list(cases)
    random.Random(seed).shuffle(shuffled)
    con = duckdb.connect()
    assert run_grid(con, cases) == run_grid(con, shuffled)


def test_req_sens_run_1_the_default_grid_point_equals_the_pipeline_headline_run(tmp_path):
    """On the sample, the grid point with the default parameters has the same tier counts as the exported run."""
    import json

    from undead311.pipeline import run_pipeline

    out = tmp_path / "out"
    rep = run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "d", run_time="2026-11-13T00:00:00Z")
    db = duckdb.connect(str(tmp_path / "d" / "processed-sample" / "undead311.duckdb"), read_only=True)
    row = db.execute("select headline, source_unknown, sensitivity from grid_run_index where run_id = ?", [run_id(DEFAULT)]).fetchone()
    assert row == (rep.tier_counts["headline"], rep.tier_counts["source_unknown"], rep.tier_counts["sensitivity"])
    assert db.execute("select count(*) from grid_run_index").fetchone()[0] == 19
    assert json.loads((out / "status.json").read_text())["headline_count"] == row[0]
