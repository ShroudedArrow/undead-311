"""REQ-EXP-SIZE.1-2: card shards, deterministic `.gz` copies, reported sizes and the first-view budget."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_export import town_inputs

from undead311.export.writers import (
    FIRST_VIEW_BUDGET_BYTES,
    FIRST_VIEW_FILES,
    PayloadBudgetExceeded,
    check_first_view_budget,
    export_all,
    first_view_bytes,
    gzip_bytes,
    write_gz_copy,
)


def test_req_exp_size_1_every_json_file_has_a_gz_twin_with_the_same_bytes(tmp_path):
    result, cases, ctx = town_inputs()
    written = export_all(result, cases, tmp_path, ctx)
    jsons = [p for p in written if p.suffix == ".json"]
    assert jsons and all(p.with_name(p.name + ".gz") in written for p in jsons)
    for p in jsons:
        assert gzip.decompress(p.with_name(p.name + ".gz").read_bytes()) == p.read_bytes()
    assert not list(tmp_path.rglob("*.tmp"))


def test_req_exp_size_1_status_is_still_the_last_file_written_and_gz_files_are_identical_between_runs(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    written = export_all(*town_inputs()[:2], a, town_inputs()[2])
    export_all(*town_inputs()[:2], b, town_inputs()[2])
    assert written[-1].name == "status.json" and written[-2].name == "status.json.gz"
    assert {str(p.relative_to(a)): p.read_bytes() for p in a.rglob("*.gz")} == {
        str(p.relative_to(b)): p.read_bytes() for p in b.rglob("*.gz")
    }


def test_req_exp_size_1_cards_are_sharded_by_neighborhood_and_year(tmp_path):
    result, cases, ctx = town_inputs()
    written = export_all(result, cases, tmp_path, ctx)
    shards = sorted(p.name for p in written if p.parent.name == "cards" and p.suffix == ".json")
    assert shards and all(len(n.removesuffix(".json").rsplit("-", 1)[1]) == 4 for n in shards)  # <neighborhood>-<year>
    for p in (p for p in written if p.parent.name == "cards" and p.suffix == ".json"):
        stem = p.stem
        year = int(stem.rsplit("-", 1)[1])
        assert {c["resurrection_date"][:4] for c in json.loads(p.read_text())["cards"]} == {str(year)}


def test_req_exp_size_1_stats_files_written_before_the_export_get_gz_copies(tmp_path):
    (tmp_path / "stats").mkdir()
    (tmp_path / "stats" / "scorecard.json").write_text('{"scorecards":[]}\n')
    result, cases, ctx = town_inputs()
    written = export_all(result, cases, tmp_path, ctx)
    assert tmp_path / "stats" / "scorecard.json.gz" in written
    assert gzip.decompress((tmp_path / "stats" / "scorecard.json.gz").read_bytes()) == b'{"scorecards":[]}\n'


def test_req_exp_size_2_first_view_over_budget_fails_before_anything_is_written(tmp_path):
    (tmp_path / "stats").mkdir()
    (tmp_path / "stats" / "scorecard.json").write_text(" " * (FIRST_VIEW_BUDGET_BYTES + 1))
    result, cases, ctx = town_inputs()
    with pytest.raises(PayloadBudgetExceeded, match="over the 3,000,000 B budget"):
        export_all(result, cases, tmp_path, ctx)
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["scorecard.json"]  # nothing new, no status


def test_req_exp_size_2_the_check_counts_only_first_view_files_and_is_inclusive():
    sizes = {"status.json": 10, "points.json": 20, "cards/x-2020.json": 10**9, "zombies.json": 10**9}
    assert check_first_view_budget(sizes) == first_view_bytes(sizes) == 30
    assert check_first_view_budget({"points.json": 100}, budget=100) == 100
    with pytest.raises(PayloadBudgetExceeded):
        check_first_view_budget({"points.json": 101}, budget=100)


@given(st.dictionaries(st.sampled_from([*FIRST_VIEW_FILES, "zombies.json", "cards/a-2020.json"]), st.integers(0, 2_000_000)))
def test_req_exp_size_2_budget_check_agrees_with_the_sum_of_first_view_sizes(sizes):
    over = sum(n for k, n in sizes.items() if k in FIRST_VIEW_FILES) > FIRST_VIEW_BUDGET_BYTES
    try:
        check_first_view_budget(sizes)
        raised = False
    except PayloadBudgetExceeded:
        raised = True
    assert raised == over


@given(st.binary(max_size=2000))
def test_req_exp_size_1_gzip_is_deterministic_and_lossless(data):
    assert gzip_bytes(data) == gzip_bytes(data) and gzip.decompress(gzip_bytes(data)) == data


def test_req_exp_size_1_write_gz_copy_can_precede_its_file(tmp_path):
    target = tmp_path / "sub" / "status.json"
    gz = write_gz_copy(target, b"{}\n")
    assert gz.name == "status.json.gz" and not target.exists() and gzip.decompress(gz.read_bytes()) == b"{}\n"


def test_req_exp_size_2_the_run_report_lists_every_file_size_and_the_first_view_total(tmp_path):
    from undead311.pipeline import run_pipeline

    out = tmp_path / "out"
    rep = run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "d", run_time="2026-11-13T00:00:00Z", grid=False)
    on_disk = {p.relative_to(out).as_posix(): p.stat().st_size for p in Path(out).rglob("*") if p.is_file()}
    assert rep.file_sizes == {k: v for k, v in on_disk.items() if k in rep.file_sizes} and "status.json.gz" in rep.file_sizes
    assert all(n in rep.file_sizes for n in on_disk)  # nothing exported goes unreported
    assert 0 < rep.first_view_bytes <= rep.first_view_budget_bytes == FIRST_VIEW_BUDGET_BYTES
    assert f"first view {rep.first_view_bytes:,}" in rep.summary()
    run_report = json.loads((tmp_path / "d" / "processed-sample" / "run_report.json").read_text())
    assert run_report["first_view_bytes"] == rep.first_view_bytes
