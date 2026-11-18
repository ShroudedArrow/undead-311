"""Stage runner and resumable pipeline (REQ-OPS-RUN.1-4)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from helpers import read_zombies
from test_pipeline import raw_folder

import undead311.pipeline as pl
from undead311.pipeline import run_pipeline
from undead311.stages import MARKER_TABLE, StageRunner, fingerprint, prepare

RUN = {"run_time": "2026-11-13T00:00:00Z"}


def persistent(tmp_path, log=None):
    """A runner bound to a file database, as the full run uses it."""
    con = duckdb.connect(str(tmp_path / "p.duckdb"))
    runner = StageRunner(tmp_path / "stages", log or (lambda *_: None))
    runner.attach(con)
    return con, runner


def test_req_ops_run_1_a_plain_runner_times_a_stage_and_returns_its_delta():
    """REQ-OPS-RUN.1: no database, no markers; the record has seconds, a sampled peak and the stage's rows."""
    lines: list[str] = []
    runner = StageRunner(log=lines.append)
    delta = runner.run("load", lambda: {"row_counts": {"raw_legacy": 7}, "stage_rows": {"extra": 2}})
    assert delta["row_counts"] == {"raw_legacy": 7}
    rec = runner.records[0]
    assert rec["stage"] == "load" and rec["status"] == "done" and rec["rows"] == {"raw_legacy": 7, "extra": 2}
    assert rec["seconds"] >= 0 and rec["peak_rss_mb"] > 0 and rec["process_peak_mb"] >= rec["peak_rss_mb"] * 0.5
    assert lines and "[stage] load" in lines[0] and "raw_legacy=7" in lines[0]


def test_req_ops_run_2_a_finished_stage_is_skipped_on_restart_and_returns_the_stored_delta(tmp_path):
    """REQ-OPS-RUN.2: the second process does not call the function and gets the first process's delta."""
    con, runner = persistent(tmp_path)
    calls = []
    runner.run("a", lambda: calls.append("a") or {"row_counts": {"x": 1}, "warnings": ["w"]}, tables=())
    con.close()
    con2, runner2 = persistent(tmp_path)
    assert runner2.done("a")
    delta = runner2.run("a", lambda: calls.append("again") or {})
    assert calls == ["a"] and delta == {"row_counts": {"x": 1}, "warnings": ["w"]}
    assert runner2.records[0]["status"] == "skipped"
    con2.close()


def test_req_ops_run_2_a_stage_that_fails_leaves_neither_its_tables_nor_a_marker(tmp_path):
    """REQ-OPS-RUN.2: the stage and its marker share one transaction, so a crash cannot leave half a stage."""
    con, runner = persistent(tmp_path)

    def bad():
        con.execute("create table half(x int)")
        con.execute("insert into half values (1)")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        runner.run("b", bad)
    assert not runner.done("b")
    assert con.execute("select count(*) from information_schema.tables where table_name = 'half'").fetchone()[0] == 0
    assert con.execute(f"select count(*) from {MARKER_TABLE}").fetchone()[0] == 0
    assert runner.run("b", lambda: {"row_counts": {"ok": 1}})["row_counts"] == {"ok": 1}  # the retry works
    con.close()


def test_req_ops_run_2_done_markers_are_written_as_readable_files_with_time_memory_and_rows(tmp_path):
    """REQ-OPS-RUN.3: `NN-<stage>.done.json` per finished stage."""
    con, runner = persistent(tmp_path)
    con.execute("create table t as select range as x from range(5)")
    runner.run("one", dict, tables=("t",))
    runner.run("two", lambda: {"row_counts": {"n": 3}})
    files = sorted(p.name for p in (tmp_path / "stages").glob("*.done.json"))
    assert files == ["01-one.done.json", "02-two.done.json"]
    rec = json.loads((tmp_path / "stages" / "01-one.done.json").read_text())
    assert rec["rows"] == {"t": 5} and rec["seconds"] >= 0 and rec["peak_rss_mb"] > 0 and rec["finished_utc"].endswith("Z")
    con.close()


def test_req_ops_run_2_a_stage_progress_callback_gets_every_finished_stage_and_its_failure_is_ignored(tmp_path):
    """REQ-OPS-RUN.4: the callback (the run-log comment) cannot stop the run."""
    seen: list[str] = []
    lines: list[str] = []

    def hook(rec):
        seen.append(rec["stage"])
        raise OSError("github unreachable")

    runner = StageRunner(log=lines.append, on_stage=hook)
    runner.run("a", dict)
    runner.always("b", dict)
    assert seen == ["a", "b"] and any("callback failed" in x for x in lines)


def test_req_ops_run_2_prepare_resumes_only_with_the_same_inputs(tmp_path):
    """REQ-OPS-RUN.2: a different fingerprint, or markers without a database, mean a fresh start."""
    stages, db = tmp_path / "stages", tmp_path / "x.duckdb.tmp"
    fp1, fp2 = fingerprint("snap", "{}", {"a.csv": 1}), fingerprint("snap2", "{}", {"a.csv": 1})
    assert fp1 != fp2 and fp1 != fingerprint("snap", "{}", {"a.csv": 2}) and fp1 != fingerprint("snap", '{"p":1}', {"a.csv": 1})
    quiet = lambda *_: None
    assert prepare(stages, db, fp1, quiet) is False  # nothing there yet
    db.write_bytes(b"db")
    (stages / "01-load.done.json").write_text("{}")
    assert prepare(stages, db, fp1, quiet) is True and db.exists()
    assert prepare(stages, db, fp2, quiet) is False  # inputs changed: partial build and markers are removed
    assert not db.exists() and not list(stages.glob("*.done.json"))
    (stages / "01-load.done.json").write_text("{}")
    assert prepare(stages, db, fp2, quiet) is False and not list(stages.glob("*.done.json"))  # markers but no database


def plain_and_resumed(tmp_path, monkeypatch, fail_at: str):
    """Run once with `fail_at` raising after some stages committed, then again without the failure."""
    raw, snap = raw_folder(tmp_path)
    kw = {"raw_dir": raw, "snapshot_md": snap, **RUN}
    plain = run_pipeline(out_dir=tmp_path / "o-plain", work_dir=tmp_path / "d-plain", **kw)
    stages = tmp_path / "stages"
    real = getattr(pl, fail_at)

    def boom(*a, **k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(pl, fail_at, boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_pipeline(out_dir=tmp_path / "o-res", work_dir=tmp_path / "d-res", stages_dir=stages, **kw)
    monkeypatch.setattr(pl, fail_at, real)
    return plain, kw, stages


def test_req_ops_run_3_a_restart_skips_the_finished_stages_and_matches_an_uninterrupted_run(tmp_path, monkeypatch):
    """REQ-OPS-RUN.2-3: crash in the detect step; the restart reuses load..bulk and exports what a plain run exports."""
    ref, kw, stages = plain_and_resumed(tmp_path, monkeypatch, "sql_edges")
    first_markers = sorted(p.name for p in stages.glob("*.done.json"))
    assert first_markers[:3] == ["01-load.done.json", "02-normalize.done.json", "03-crosswalk.done.json"]
    assert any(m.endswith("-bulk.done.json") for m in first_markers) and not any("grid" in m for m in first_markers)

    def must_not_reload(*a, **k):
        raise AssertionError("load ran again although its marker was committed")

    monkeypatch.setattr(pl, "load", must_not_reload)
    monkeypatch.setattr(pl, "normalize", must_not_reload)
    res = run_pipeline(out_dir=tmp_path / "o-res", work_dir=tmp_path / "d-res", stages_dir=stages, **kw)
    skipped = {r["stage"] for r in res.stages if r["status"] == "skipped"}
    assert {"load", "normalize", "crosswalk", "clean", "snap", "neighborhoods", "coroner", "bulk"} <= skipped
    plain = read_zombies(tmp_path / "o-plain")
    assert read_zombies(tmp_path / "o-res") == plain
    for field in ("row_counts", "exclusions", "excluded_pairs", "tier_counts", "label_coverage", "unlabeled", "warnings",
                  "normalization_issues", "pii_counts"):  # fmt: skip
        assert getattr(res, field) == getattr(ref, field), field


def test_req_ops_run_2_a_restart_after_a_failure_in_the_export_step_resumes_from_the_grid(tmp_path, monkeypatch):
    """REQ-OPS-RUN.2: the grid stage is expensive on the full data; once committed it is not run again."""
    _plain, kw, stages = plain_and_resumed(tmp_path, monkeypatch, "export_all")
    done = sorted(p.name for p in stages.glob("*.done.json"))
    assert any(n.endswith("-grid.done.json") for n in done) and sum("-grid-" in n for n in done) == 7
    monkeypatch.setattr(pl, "run_grid_group", lambda *a, **k: (_ for _ in ()).throw(AssertionError("grid ran again")))
    res = run_pipeline(out_dir=tmp_path / "o-res", work_dir=tmp_path / "d-res", stages_dir=stages, **kw)
    assert res.ok and "grid" in {r["stage"] for r in res.stages if r["status"] == "skipped"}
    assert res.row_counts["grid_runs"] > 0  # the stored delta restored the count


def test_req_ops_run_2_changed_inputs_discard_the_partial_build(tmp_path, monkeypatch):
    """REQ-OPS-RUN.2: a new SNAPSHOT.md means a different download; nothing from the old partial build is reused."""
    _plain, kw, stages = plain_and_resumed(tmp_path, monkeypatch, "sql_edges")
    Path(kw["snapshot_md"]).write_text(Path(kw["snapshot_md"]).read_text().replace("2026-11-12", "2026-11-16"))
    lines: list[str] = []
    res = run_pipeline(out_dir=tmp_path / "o-res", work_dir=tmp_path / "d-res", stages_dir=stages, log=lines.append, **kw)
    assert res.ok and not [r for r in res.stages if r["status"] == "skipped"]
    assert any("inputs changed" in x for x in lines)


def test_req_ops_run_1_the_run_report_lists_every_stage_with_time_memory_and_rows(tmp_path):
    """REQ-OPS-RUN.1: run_report.json carries the stage table the run-log comments are built from."""
    raw, snap = raw_folder(tmp_path)
    rep = run_pipeline(out_dir=tmp_path / "o", work_dir=tmp_path / "d", raw_dir=raw, snapshot_md=snap, stages_dir=tmp_path / "s", **RUN)
    stored = json.loads((tmp_path / "d" / "processed" / "run_report.json").read_text())["stages"]
    names = [r["stage"] for r in stored]
    assert names[:4] == ["load", "normalize", "crosswalk", "clean"] and names[-1] == "export"
    for r in stored:
        assert {"seconds", "peak_rss_mb", "rows", "status"} <= set(r) and "delta" not in r
    assert rep.stages == stored
    assert next(r for r in stored if r["stage"] == "load")["rows"] == {"raw_legacy": 4, "raw_new": 1}
    assert next(r for r in stored if r["stage"] == "coroner")["rows"]["closed_in_scope"] >= 0


def test_req_ops_run_2_marker_tables_stay_out_of_the_snapshot_row_counts(tmp_path):
    """REQ-OPS-SNAP.1: `_stage_done` and `_run_meta` are bookkeeping, not data."""
    from undead311 import snapshot as snap_mod

    raw, snap = raw_folder(tmp_path)
    run_pipeline(out_dir=tmp_path / "o", work_dir=tmp_path / "d", raw_dir=raw, snapshot_md=snap, stages_dir=tmp_path / "s", **RUN)
    counts = snap_mod.table_row_counts(tmp_path / "d" / "processed" / "undead311.duckdb")
    assert "cases_clean" in counts and not [t for t in counts if t.startswith("_")]


def test_req_ops_run_4_the_runner_names_the_stage_that_raised():
    """REQ-OPS-RUN.4: `current` stays set after an exception, so run_full can count failures per stage."""
    runner = StageRunner(log=lambda *_: None)
    runner.run("fine", dict)
    assert runner.current is None
    with pytest.raises(ValueError, match="x"):
        runner.run("breaks", lambda: (_ for _ in ()).throw(ValueError("x")))
    assert runner.current == "breaks"


# ---- run_full.py and the Coroner coverage list (REQ-OPS-RUN.4-5) ------------------------------------------------------

import importlib.util

from undead311.coroner.join import join_labels, unlabeled_templates

_spec = importlib.util.spec_from_file_location("run_full", Path(__file__).parents[2] / "scripts" / "run_full.py")
run_full = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_full)


def closed_table(rows):
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, status varchar, closure_code varchar, closure_text varchar, coroner_label varchar)")
    con.executemany("insert into cases_clean values (?,?,?,?,?,NULL)", rows)
    return con


def test_req_ops_run_5_unlabeled_templates_are_ranked_by_case_count_with_the_coverage_summary(tmp_path):
    """REQ-OPS-RUN.5: same rule as join_labels; labeled templates, code-labeled new cases and open cases are not listed."""
    labels = tmp_path / "labels.csv"
    labels.write_text("template,label\nresolved,resolved\n")
    rows = [(f"1{i}", "legacy", "Closed", None, "Mystery text 5") for i in range(3)]  # masks to "mystery text <n>"
    rows += [(f"2{i}", "legacy", "Closed", None, "Mystery text 9") for i in range(2)]  # same template as above
    rows += [("30", "legacy", "Closed", None, "Another one"), ("31", "new", "Closed", None, "Another one")]
    rows += [("40", "legacy", "Closed", None, "Resolved"), ("41", "new", "Closed", "Resolved", ""), ("42", "legacy", "Open", None, "x")]
    con = closed_table(rows)
    listed, summary = unlabeled_templates(con, labels, top=5)
    assert [(r["template"], r["n_cases"]) for r in listed] == [("mystery text <n>", 5), ("another one", 2)]
    assert listed[1]["systems"] == "legacy:1;new:1"
    assert summary["closed_in_scope"] == 9 and summary["unlabeled"] == 7 and summary["listed_cases"] == 7
    assert summary["coverage"] == pytest.approx(2 / 9) and summary["coverage_if_listed_were_labeled"] == 1.0
    assert unlabeled_templates(con, labels, top=1)[0][0]["template"] == "mystery text <n>"
    jr = join_labels(con, labels)  # the two functions agree on what is unlabeled
    assert jr.unlabeled == summary["unlabeled"] and jr.closed_in_scope == summary["closed_in_scope"]


def test_req_ops_run_4_a_comment_that_cannot_be_posted_is_queued_and_sent_with_the_next(tmp_path, monkeypatch):
    """REQ-OPS-RUN.4: GitHub down never stops the run; the queue is flushed in order when it is back."""
    import sys

    sent: list[str] = []
    state = {"up": False}

    class FakeHooklib:
        @staticmethod
        def gh_request(method, path, body=None):
            if not state["up"]:
                raise OSError("no route")
            sent.append(body["body"])

    monkeypatch.setitem(sys.modules, "hooklib", FakeHooklib)
    ch = run_full.Channel("full-1", 7, tmp_path / "pending.jsonl")
    assert ch.post("first") is False and sent == []
    state["up"] = True
    assert ch.post("second") is True and sent == ["first", "second"]
    assert (tmp_path / "pending.jsonl").read_text() == ""
    assert run_full.Channel("full-1", None, tmp_path / "p2.jsonl").post("x") is False  # no issue number: queued, no crash


def test_req_ops_run_4_the_stage_comment_has_time_rows_and_peak_memory():
    """REQ-OPS-RUN.4."""
    rec = {"stage": "snap", "seconds": 64.3, "peak_rss_mb": 1057.2, "process_peak_mb": 1100.0, "rows": {"snapped_cases": 26792}, "finished_utc": "2026-11-16T04:00:00Z"}
    summary, evidence = run_full.stage_comment(rec)
    assert "64.3 s" in summary and "1,057 MB" in summary and "snapped_cases 26,792" in evidence
    body = run_full.Channel("full-1", 1, Path("/nonexistent/x")).body("status", summary, evidence)
    assert body.startswith("```yaml\nfrom: engine\nto: human\ntype: status\nrun: full-1") and len(body.split()) < 200


def run_main(tmp_path, monkeypatch, *extra):
    raw, snap = (tmp_path / "raw", tmp_path / "SNAPSHOT.md") if (tmp_path / "raw").exists() else raw_folder(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(exist_ok=True)
    return run_full.main(["--run-id", "t1", "--raw", str(raw), "--snapshot-md", str(snap),
                          "--done-file", str(tmp_path / "t1.done.json"), *extra])


def test_req_ops_run_1_run_full_logs_to_data_dir_writes_markers_and_the_coverage_files(tmp_path, monkeypatch):
    """REQ-OPS-RUN.1, REQ-OPS-RUN.5: log under DATA_DIR/logs, one marker per stage, coverage and the unlabeled list."""
    import sys

    before = sys.stdout
    assert run_main(tmp_path, monkeypatch) == 0
    assert sys.stdout is before  # the tee is undone
    data = tmp_path / "data"
    log = (data / "logs" / "t1.log").read_text()
    assert "[stage] load" in log and "[stage] export" in log and "Coroner coverage" in log and "duckdb settings" in log
    assert (data / "logs" / "t1.stages" / "01-load.done.json").is_file()
    cov = json.loads((data / "reports" / "t1" / "coverage.json").read_text())
    assert cov["closed_in_scope"] == 1 and 0 <= cov["coverage"] <= 1
    header = (data / "reports" / "t1" / "unlabeled_templates_top300.csv").read_text().splitlines()[0]
    assert header == "template,n_cases,example_id,systems,example_text"
    assert (data / "exports" / "t1" / "zombies" / "index.json").is_file()
    assert (data / "logs" / "t1.comments-pending.jsonl").exists()  # no issue number: every comment was queued


def test_req_ops_run_4_a_stage_that_fails_twice_stops_the_run_and_leaves_everything_in_place(tmp_path, monkeypatch):
    """REQ-OPS-RUN.4: first failure exits 1 (restart once), the second exits 2 and writes STOPPED; a third start refuses."""
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk on fire"))
    monkeypatch.setattr(pl, "sql_edges", boom)
    assert run_main(tmp_path, monkeypatch) == 1
    data = tmp_path / "data" / "logs"
    assert json.loads((data / "t1.attempts.json").read_text()) == {"detect": 1} and not (data / "t1.STOPPED").exists()
    assert run_main(tmp_path, monkeypatch) == 2 and (data / "t1.STOPPED").exists()
    stages_before = sorted(p.name for p in (data / "t1.stages").glob("*.done.json"))
    assert stages_before and (tmp_path / "data" / "processed" / "undead311.duckdb.tmp").exists()  # nothing was deleted
    assert run_main(tmp_path, monkeypatch) == 2  # refuses to start
    assert "stage detect failed" not in (data / "t1.log").read_text() and "failed twice" in (data / "t1.log").read_text()
    pending = (data / "t1.comments-pending.jsonl").read_text()
    assert "failure 2 of 2" in pending and "Run stopped, nothing deleted" in pending


def test_req_ops_run_2_run_full_resumes_after_a_failure_and_finishes(tmp_path, monkeypatch):
    """REQ-OPS-RUN.2: one failure, then a restart with the same command skips the finished stages."""
    real = pl.sql_edges
    monkeypatch.setattr(pl, "sql_edges", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("once")))
    assert run_main(tmp_path, monkeypatch) == 1
    monkeypatch.setattr(pl, "sql_edges", real)
    assert run_main(tmp_path, monkeypatch) == 0
    log = (tmp_path / "data" / "logs" / "t1.log").read_text()
    assert "resume: found a partial build" in log and "skipped" in log
    assert json.loads((tmp_path / "data" / "reports" / "t1" / "coverage.json").read_text())["closed_in_scope"] == 1


def tree_state(root: Path) -> dict[str, tuple[int, int]]:
    """(size, mtime in ns) of every file under `root`, to prove that nothing was written, rewritten or deleted."""
    return {f.relative_to(root).as_posix(): (f.stat().st_size, f.stat().st_mtime_ns) for f in sorted(root.rglob("*")) if f.is_file()}


def test_req_ops_run_7_a_run_whose_done_file_says_done_exits_at_once_and_discards_nothing(tmp_path, monkeypatch):
    """REQ-OPS-RUN.7: rehearsal-1 ran a second pass; a leg started after the run finished must not touch it. Same command,
    done file with `done: true`: exit 0, no stage, no write, no delete (done file, markers, logs, database, exports, reports)."""
    assert run_main(tmp_path, monkeypatch) == 0
    done = tmp_path / "t1.done.json"
    assert json.loads(done.read_text())["done"] is True
    before = tree_state(tmp_path / "data") | {"done": (done.stat().st_size, done.stat().st_mtime_ns)}

    def boom(*a, **k):
        raise AssertionError("a finished run must not run the pipeline again")

    monkeypatch.setattr(run_full, "run_pipeline", boom)
    assert run_main(tmp_path, monkeypatch) == 0
    assert tree_state(tmp_path / "data") | {"done": (done.stat().st_size, done.stat().st_mtime_ns)} == before


def test_req_ops_run_7_only_a_done_true_file_of_this_run_ends_a_run_early(tmp_path):
    """REQ-OPS-RUN.7: a missing, damaged, `done: false`, or other run's file does not count as done."""
    f = tmp_path / "x.done.json"
    assert not run_full.already_done(f, "r1")
    f.write_text("{not json")
    assert not run_full.already_done(f, "r1")
    f.write_text(json.dumps({"run_id": "r1", "done": False, "exit_code": 4}))
    assert not run_full.already_done(f, "r1")
    f.write_text(json.dumps({"run_id": "r2", "done": True}))
    assert not run_full.already_done(f, "r1")
    f.write_text(json.dumps({"run_id": "r1", "done": "true"}))  # a string is not the boolean the loop's stopCondition tests
    assert not run_full.already_done(f, "r1")
    f.write_text(json.dumps({"run_id": "r1", "done": True}))
    assert run_full.already_done(f, "r1")


def test_req_ops_run_8_a_leg_killed_after_the_pipeline_finished_does_not_rebuild_everything(tmp_path, monkeypatch):
    """REQ-OPS-RUN.8 (rehearsal-1, leg 3 to 4): the 30-minute cap ended a leg after the database was renamed but before the
    done file was written. The next leg saw markers and no partial database, called that a fresh start and rebuilt all
    stages (a second pass of about 3 hours). Now it reads the stored report, writes the coverage and the done file, and
    every stage ran exactly once."""
    real = run_full.unlabeled_templates
    monkeypatch.setattr(run_full, "unlabeled_templates", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        run_main(tmp_path, monkeypatch)  # the pipeline finished; the process dies before the coverage report
    data, stages = tmp_path / "data", tmp_path / "data" / "logs" / "t1.stages"
    assert (data / "processed" / "undead311.duckdb").is_file() and not (data / "processed" / "undead311.duckdb.tmp").exists()
    assert (stages / "complete.json").is_file() and json.loads((tmp_path / "t1.done.json").read_text())["done"] is False
    markers = tree_state(stages)

    monkeypatch.setattr(run_full, "unlabeled_templates", real)
    assert run_main(tmp_path, monkeypatch) == 0
    log = (data / "logs" / "t1.log").read_text()
    assert "already finished with the same inputs" in log and "fresh start" not in log
    assert log.count("[stage] load") == 1 and log.count("[stage] export") == 1  # nothing ran twice
    assert {k: v for k, v in tree_state(stages).items() if k != "complete.json"} == {k: v for k, v in markers.items() if k != "complete.json"}
    assert json.loads((tmp_path / "t1.done.json").read_text())["done"] is True
    assert not (stages / "complete.json").exists()  # consumed: a later explicit rerun is a fresh run, as before
    assert json.loads((data / "reports" / "t1" / "coverage.json").read_text())["closed_in_scope"] == 1


def test_req_ops_run_8_without_reuse_a_finished_database_is_still_a_fresh_start(tmp_path):
    """REQ-OPS-RUN.8: `reuse_complete` is opt-in; run_pipeline called as before rebuilds (nothing else changes)."""
    raw, snap = raw_folder(tmp_path)
    kw = {"raw_dir": raw, "snapshot_md": snap, "work_dir": tmp_path / "d", "stages_dir": tmp_path / "stages", **RUN}
    first = run_pipeline(out_dir=tmp_path / "o", **kw)
    assert (tmp_path / "stages" / "complete.json").is_file()
    lines: list[str] = []
    again = run_pipeline(out_dir=tmp_path / "o", log=lines.append, **kw)
    assert any("fresh start" in x for x in lines) and again.tier_counts == first.tier_counts
    reused: list[str] = []
    third = run_pipeline(out_dir=tmp_path / "o", log=reused.append, reuse_complete=True, **kw)
    assert any("not rebuilding" in x for x in reused) and third.tier_counts == first.tier_counts


def test_req_ops_run_8_changed_inputs_never_reuse_a_complete_run(tmp_path):
    """REQ-OPS-RUN.8: the marker names the inputs' fingerprint; a different raw file size is a fresh start."""
    raw, snap = raw_folder(tmp_path)
    kw = {"raw_dir": raw, "snapshot_md": snap, "work_dir": tmp_path / "d", "stages_dir": tmp_path / "stages", **RUN}
    run_pipeline(out_dir=tmp_path / "o", **kw)
    victim = min(raw.glob("311_*.csv"))
    victim.write_text(victim.read_text() + "\n")
    lines: list[str] = []
    run_pipeline(out_dir=tmp_path / "o", log=lines.append, reuse_complete=True, **kw)
    assert any("fresh start" in x for x in lines) and not any("not rebuilding" in x for x in lines)


def test_req_ops_run_4_the_kill_switch_file_stops_the_run_before_it_starts(tmp_path, monkeypatch):
    """REQ-OPS-RUN.4 (structure.md kill switch)."""
    stop = Path(run_full.worktree_root()) / ".kiro" / "STOP"
    monkeypatch.setattr(run_full, "worktree_root", lambda: tmp_path / "fake-root")
    (tmp_path / "fake-root" / ".kiro").mkdir(parents=True)
    (tmp_path / "fake-root" / ".kiro" / "STOP").write_text("")
    assert not stop.exists()  # the real repo has no STOP file
    assert run_main(tmp_path, monkeypatch) == 3


def test_req_ops_run_2_a_grid_split_into_committed_groups_equals_one_pass_and_resumes_mid_grid(tmp_path, monkeypatch):
    """REQ-OPS-RUN.2, REQ-SENS-RUN.1: the 7 grid groups give the same grid tables as `run_grid`, and a crash in the 4th group
    reruns only groups 4 to 7."""
    from undead311.detect import grid as grid_mod

    raw, snap = raw_folder(tmp_path)
    kw = {"raw_dir": raw, "snapshot_md": snap, **RUN}
    run_pipeline(out_dir=tmp_path / "o1", work_dir=tmp_path / "d1", **kw)
    con = duckdb.connect(str(tmp_path / "d1" / "processed" / "undead311.duckdb"), read_only=True)
    stored = con.execute("select * from grid_run_index order by run_id").fetchall()
    cases = pl.cases_from_table(con, "cases_clean")
    expected = sorted(r.run_id for r in grid_mod.run_grid(con, cases))
    con.close()
    assert sorted(r[0] for r in stored) == expected and len(expected) == 19

    real, calls, crashed = pl.run_grid_group, [], []

    def flaky(con, cases, group, *a, **k):
        calls.append(group)
        if group == "radius-r15" and not crashed:
            crashed.append(group)
            raise RuntimeError("cap reached")
        return real(con, cases, group, *a, **k)

    monkeypatch.setattr(pl, "run_grid_group", flaky)
    stages = tmp_path / "stages"
    with pytest.raises(RuntimeError, match="cap reached"):
        run_pipeline(out_dir=tmp_path / "o2", work_dir=tmp_path / "d2", stages_dir=stages, **kw)
    assert calls == ["segment-r15", "segment-r30", "segment-r50", "radius-r15"]
    calls.clear()
    run_pipeline(out_dir=tmp_path / "o2", work_dir=tmp_path / "d2", stages_dir=stages, **kw)
    assert calls == ["radius-r15", "radius-r30", "radius-r50", "no-street-light-other"]
    con = duckdb.connect(str(tmp_path / "d2" / "processed" / "undead311.duckdb"), read_only=True)
    assert con.execute("select * from grid_run_index order by run_id").fetchall() == stored
    con.close()
    assert (tmp_path / "o2" / "stats" / "sensitivity_grid.json").read_text() == (tmp_path / "o1" / "stats" / "sensitivity_grid.json").read_text()


def test_req_ops_run_4_a_time_budget_stops_cleanly_after_a_stage_and_the_next_start_resumes(tmp_path, monkeypatch):
    """REQ-OPS-RUN.4: budget 0 stops after the first committed stage (exit 4, no failure recorded); a second start finishes."""
    assert run_main(tmp_path, monkeypatch, "--budget-min", "0") == 4  # main returns the exit code and writes the done file
    done = json.loads((tmp_path / "t1.done.json").read_text())  # REQ-OPS-RUN.6: a budget stop is not done
    assert done["done"] is False and done["status"] == "budget" and done["exit_code"] == 4 and done["stages_committed"] == 1
    logs = tmp_path / "data" / "logs"
    assert [p.name for p in (logs / "t1.stages").glob("*.done.json")] == ["01-load.done.json"]
    assert not (logs / "t1.attempts.json").exists() and not (logs / "t1.STOPPED").exists()
    assert run_main(tmp_path, monkeypatch) == 0
    assert "resume: found a partial build" in (logs / "t1.log").read_text()
    done = json.loads((tmp_path / "t1.done.json").read_text())
    assert done["done"] is True and done["status"] == "finished" and done["next"] == "none"  # REQ-OPS-RUN.6


def test_req_ops_run_4_the_budget_never_stops_after_an_unmarked_step(tmp_path, monkeypatch):
    """REQ-OPS-RUN.4: with every committed stage already done, budget 0 still finishes (detect, stats and export have no
    marker, so stopping after them would redo them on every leg)."""
    assert run_main(tmp_path, monkeypatch) == 0
    for p in (tmp_path / "data" / "processed").glob("undead311.duckdb*"):
        p.unlink()
    (tmp_path / "data" / "logs" / "t1.stages" / "fingerprint.txt").unlink()  # fresh start
    (tmp_path / "t1.done.json").unlink()  # REQ-OPS-RUN.7: a finished run is not started again unless its done file is removed
    assert run_main(tmp_path, monkeypatch, "--budget-min", "0") == 4  # stops after load, a committed stage
    monkeypatch.setattr(run_full, "StageRunner", run_full.StageRunner)
    # second leg: only unmarked steps and later stages remain; the budget fires after the next committed stage, never
    # after `detect` or `export`
    assert run_main(tmp_path, monkeypatch, "--budget-min", "0") == 4
    log = (tmp_path / "data" / "logs" / "t1.log").read_text()
    stops = [line for line in log.splitlines() if "time budget" in line]
    assert stops and not any("after stage detect" in s or "after stage export" in s or "after stage templates" in s for s in stops)


def test_req_exp_size_2_the_dry_run_override_writes_an_over_budget_view_with_an_anomaly(tmp_path, monkeypatch):
    """REQ-EXP-SIZE.2 (owner decision 2026-11-16, option D): without the override the run fails on the budget; with
    `--dry-run-over-budget` it writes the files and status.json names the overrun."""
    from undead311.export import writers

    monkeypatch.setattr(writers, "FIRST_VIEW_BUDGET_BYTES", 10)
    monkeypatch.setattr(writers.check_first_view_budget, "__defaults__", (10,))
    assert run_main(tmp_path, monkeypatch) == 1  # the gate holds by default
    assert run_main(tmp_path, monkeypatch, "--dry-run-over-budget") == 0
    status = json.loads((tmp_path / "data" / "exports" / "t1" / "status.json").read_text())
    assert any(a.startswith("DRY RUN ONLY, over the first-view budget") for a in status["anomalies"])


def test_req_exp_size_2_no_production_entry_point_can_set_the_dry_run_override():
    """REQ-EXP-SIZE.2: `make pipeline` (the CLI), the Makefile and the CI and nightly workflows never pass it."""
    from undead311.cli import build_parser

    root = Path(__file__).resolve().parents[3]
    assert "over_budget" not in " ".join(a.dest for p in build_parser()._subparsers._group_actions[0].choices.values() for a in p._actions)
    for f in [root / "Makefile", *(root / ".github" / "workflows").glob("*.yml"), *(root / "ops").rglob("*.yml")]:
        text = f.read_text()
        assert "over-budget" not in text and "over_budget" not in text, f
