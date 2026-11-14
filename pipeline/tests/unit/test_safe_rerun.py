"""REQ-ING-NIGHTLY.1: outputs are built in staging folders and swapped in only after every stage succeeded."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from test_pipeline import raw_folder

import undead311.export.writers as w
import undead311.pipeline as pl
from undead311.export.writers import Swap, _proc_start, find_staging_leftovers, staging_dir, swap_into
from undead311.pipeline import owns_output, run_pipeline

RUN = "2026-11-13T00:00:00Z"


def snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def first_run(tmp_path):
    raw, snap = raw_folder(tmp_path)
    out, work = tmp_path / "web" / "data", tmp_path / "work"
    run_pipeline(out_dir=out, raw_dir=raw, work_dir=work, snapshot_md=snap, run_time=RUN)
    return raw, snap, out, work


def again(tmp_path, raw, snap, out, work):
    return run_pipeline(out_dir=out, raw_dir=raw, work_dir=work, snapshot_md=snap, run_time="2026-11-14T00:00:00Z")


def no_staging_left(tmp_path):
    return not [p for p in tmp_path.rglob("*") if ".staging-" in p.name]


@pytest.mark.parametrize("failing", ["detect", "run_grid", "export_all", "swap_outputs"])
def test_req_ing_nightly_1_a_failed_stage_leaves_the_previous_outputs_untouched(tmp_path, monkeypatch, failing):
    raw, snap, out, work = first_run(tmp_path)
    before_out, before_work = snapshot(out), snapshot(work)
    assert "status.json" in before_out and (work / "processed" / "undead311.duckdb").is_file()

    def boom(*a, **k):
        raise RuntimeError(f"injected failure in {failing}")

    if failing == "swap_outputs":
        real = pl.Swap

        class FailingSwap(real):  # the processed files swap, then the output files fail: the first must be rolled back
            def apply(self):
                if self.target == out:
                    boom()
                return super().apply()

        monkeypatch.setattr(pl, "Swap", FailingSwap)
    else:
        monkeypatch.setattr(pl, failing, boom)
    with pytest.raises(RuntimeError, match="injected failure"):
        again(tmp_path, raw, snap, out, work)
    assert snapshot(out) == before_out  # byte for byte, including status.json
    assert snapshot(work) == before_work  # the DuckDB file, skeptic input, templates and run report too
    assert no_staging_left(tmp_path)


def test_req_ing_nightly_1_a_missing_raw_file_creates_no_output_folder(tmp_path):
    raw, snap = raw_folder(tmp_path)
    (raw / "311_2024.csv").unlink()
    out = tmp_path / "fresh" / "data"
    with pytest.raises(FileNotFoundError):
        run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "work", snapshot_md=snap, run_time=RUN)
    assert not out.exists() and no_staging_left(tmp_path)


def test_req_ing_nightly_1_a_budget_failure_leaves_the_previous_outputs_untouched(tmp_path, monkeypatch):
    import undead311.export.writers as w

    raw, snap, out, work = first_run(tmp_path)
    before = snapshot(out)
    monkeypatch.setattr(w, "FIRST_VIEW_BUDGET_BYTES", 10)
    monkeypatch.setattr(w.check_first_view_budget, "__defaults__", (10,))
    with pytest.raises(w.PayloadBudgetExceeded):
        again(tmp_path, raw, snap, out, work)
    assert snapshot(out) == before and no_staging_left(tmp_path)


def test_req_ing_nightly_1_a_good_rerun_swaps_in_new_files_removes_owned_leftovers_and_keeps_the_rest(tmp_path):
    raw, snap, out, work = first_run(tmp_path)
    (out / "cards" / "old-hood-2001.json").write_text("{}")  # a card shard this run does not produce
    (out / "cards" / "old-hood-2001.json.gz").write_bytes(b"x")
    (out / "stats" / "judge_tour.json").write_text("{}")  # a stats file the run does not produce
    (out / "sensitivity_grid.json").write_text("{}")  # not owned by the engine (durability-stats)
    (out / ".gitkeep").write_text("")
    rep = again(tmp_path, raw, snap, out, work)
    files = snapshot(out)
    assert "cards/old-hood-2001.json" not in files and "cards/old-hood-2001.json.gz" not in files
    assert "stats/judge_tour.json" not in files
    assert "sensitivity_grid.json" in files and ".gitkeep" in files
    assert '"last_run":"2026-11-14T00:00:00Z"' in files["status.json"].decode()
    assert set(rep.file_sizes) <= set(files) and "status.json.gz" in rep.file_sizes
    assert no_staging_left(tmp_path)


def test_req_ing_nightly_1_swap_writes_status_last_and_its_gz_just_before(tmp_path):
    stage = staging_dir(tmp_path / "out")
    for rel in ("status.json", "status.json.gz", "zombies.json", "cards/a-2020.json", "stats/scorecard.json"):
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / rel).write_text(rel)
    final = swap_into(stage, tmp_path / "out", owns_output)
    assert [p.relative_to(tmp_path / "out").as_posix() for p in final][-2:] == ["status.json.gz", "status.json"]
    assert sorted(p.relative_to(tmp_path / "out").as_posix() for p in final) == sorted(
        ["status.json", "status.json.gz", "zombies.json", "cards/a-2020.json", "stats/scorecard.json"]
    )
    assert not any(stage.rglob("*.json")) and (tmp_path / "out" / "zombies.json").read_text() == "zombies.json"


def test_req_ing_nightly_1_swap_never_removes_a_file_it_does_not_own(tmp_path):
    target = tmp_path / "out"
    target.mkdir()
    (target / "README.txt").write_text("keep")
    (target / "zombies.json").write_text("old")
    (target / "incidents.json").write_text("old")
    stage = staging_dir(target)
    (stage / "zombies.json").write_text("new")
    swap_into(stage, target, owns_output)
    assert (target / "README.txt").read_text() == "keep" and (target / "zombies.json").read_text() == "new"
    assert not (target / "incidents.json").exists()  # owned and no longer produced


@pytest.mark.parametrize("rel,owned", [
    ("zombies.json", True), ("zombies.json.gz", True), ("cards/x-2020.json", True), ("stats/scorecard.json.gz", True),
    ("stats/survival.json", False), ("sensitivity_grid.json", False), (".gitkeep", False), ("notes.txt", False),
])  # fmt: skip
def test_req_ing_nightly_1_ownership_rules(rel, owned):
    assert owns_output(rel) is owned


def test_req_ing_nightly_1_staging_folder_is_beside_the_target_on_the_same_filesystem(tmp_path):
    stage = staging_dir(tmp_path / "web" / "data")
    assert stage.parent == tmp_path / "web" and stage.is_dir() and os.stat(stage).st_dev == os.stat(tmp_path).st_dev


def test_req_ing_nightly_1_a_swap_that_fails_part_way_restores_every_file(tmp_path, monkeypatch):
    target = tmp_path / "out"
    (target / "cards").mkdir(parents=True)
    old = {"zombies.json": "old-z", "status.json": "old-s", "cards/stale-2020.json": "old-card", "keep.txt": "keep"}
    for rel, text in old.items():
        (target / rel).write_text(text)
    stage = staging_dir(target)
    for rel in ("zombies.json", "points.json", "status.json", "status.json.gz"):
        (stage / rel).write_text("new-" + rel)
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 7:  # fails in the middle of the status files, after other files were already replaced
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr(w.os, "replace", flaky)
    with pytest.raises(OSError, match="disk full"):
        Swap(stage, target, owns_output).apply()
    monkeypatch.undo()
    assert snapshot(target) == {k: v.encode() for k, v in old.items()}  # back to exactly the old files


def test_req_ing_nightly_1_swap_rollback_after_success_restores_the_old_files(tmp_path):
    target = tmp_path / "out"
    target.mkdir()
    (target / "zombies.json").write_text("old")
    (target / "incidents.json").write_text("old-stale")
    stage = staging_dir(target)
    (stage / "zombies.json").write_text("new")
    (stage / "points.json").write_text("new")
    swap = Swap(stage, target, owns_output).apply()
    assert snapshot(target) == {"zombies.json": b"new", "points.json": b"new"}
    swap.rollback()
    assert snapshot(target) == {"zombies.json": b"old", "incidents.json": b"old-stale"}


def test_req_ing_nightly_1_a_failed_duckdb_rename_rolls_the_swapped_files_back(tmp_path, monkeypatch):
    raw, snap, out, work = first_run(tmp_path)
    before_out, before_work = snapshot(out), snapshot(work)
    real = os.replace

    def flaky(src, dst):
        if str(dst).endswith("undead311.duckdb"):
            raise OSError("rename failed")
        return real(src, dst)

    monkeypatch.setattr(w.os, "replace", flaky)
    with pytest.raises(OSError, match="rename failed"):
        again(tmp_path, raw, snap, out, work)
    monkeypatch.undo()
    assert snapshot(out) == before_out and snapshot(work) == before_work and no_staging_left(tmp_path)


def test_req_ing_nightly_1_a_killed_runs_staging_folder_is_removed_by_the_next_run(tmp_path):
    """ops#85: a SIGKILL skips the finally cleanup; the folder of a dead pid goes, the folder of a live pid stays."""
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    dead = tmp_path / f".out.staging-{proc.pid}"
    live = tmp_path / f".out.staging-{os.getppid()}"
    other = tmp_path / f".elsewhere.staging-{proc.pid}"
    for d in (dead, live, other):
        (d / "cards").mkdir(parents=True)
        (d / "cards" / "x.json").write_text("{}")
    stage = staging_dir(tmp_path / "out")
    assert not dead.exists() and live.exists() and other.exists() and stage.is_dir()


@pytest.mark.skipif(_proc_start(os.getpid()) is None, reason="needs /proc to read a process start time")
def test_req_ing_nightly_1_a_reused_pid_does_not_keep_a_dead_runs_staging_folder(tmp_path):
    """ops#93: the name carries pid and start time. The parent is alive, so a folder with its pid but another start time
    (a reused pid) is stale, while one with its real start time belongs to a running process and stays."""
    ppid = os.getppid()
    reused = tmp_path / f".out.staging-{ppid}-1"
    running = tmp_path / f".out.staging-{ppid}-{_proc_start(ppid)}"
    for d in (reused, running):
        d.mkdir()
    staging_dir(tmp_path / "out")
    assert not reused.exists() and running.exists()


def test_req_ing_nightly_1_a_folder_with_no_start_time_expires_by_age(tmp_path):
    """ops#93: where no start time is known the pid alone is trusted only while the folder is under a day old."""
    old = tmp_path / f".out.staging-{os.getppid()}"
    old.mkdir()
    day_and_a_bit = time.time() - 25 * 3600
    os.utime(old, (day_and_a_bit, day_and_a_bit))
    staging_dir(tmp_path / "out")
    assert not old.exists()


def test_req_ing_nightly_1_a_staging_folder_is_named_for_its_process_and_is_found_under_a_tree(tmp_path):
    stage = staging_dir(tmp_path / "public" / "data")
    assert stage.name.startswith(f".data.staging-{os.getpid()}-")
    assert find_staging_leftovers(tmp_path) == [stage]
    assert find_staging_leftovers(tmp_path / "missing") == []


def test_req_ing_nightly_1_no_staging_folder_sits_in_the_shipped_web_folders():
    """ops#93: a leftover `.*.staging-*` under web/public or web/dist would ship with the static site."""
    repo = Path(__file__).resolve().parents[3]
    for folder in ("public", "dist"):
        assert find_staging_leftovers(repo / "web" / folder) == [], folder
