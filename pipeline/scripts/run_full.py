"""Full-data run with a log, resume, per-stage run-log comments and the Coroner coverage report (REQ-OPS-RUN.1-5).

  python pipeline/scripts/run_full.py --run-id full-1 [--issue N] [--out DIR] [--skip-grid]

* Output goes to `$DATA_DIR/logs/<run-id>.log` (appended) and to the console. Nothing here prints environment variables.
* Each stage commits a done-marker (`$DATA_DIR/logs/<run-id>.stages/NN-<stage>.done.json` and a row in the database). Start the
  same command again after a crash or an agent restart and it resumes after the last finished stage; changed inputs start fresh.
* After each stage a comment (time, rows, peak memory) is posted to the run-log issue in ShroudedArrow/undead-311-ops. The issue
  number comes from `--issue` or `.kiro/workflow-runs/<run-id>/channel.json`. A comment that cannot be posted is queued in
  `<run-id>.comments-pending.jsonl` and retried with the next one; GitHub being down never stops the run.
* A stage that raises twice stops the run for good (`<run-id>.STOPPED`): the failure is posted, and the database, markers and
  logs stay where they are. Delete the STOPPED file to try again.
* `.kiro/STOP` stops the run after the current stage (steering: kill switch).
* The Coroner coverage and the 300 most common unlabeled templates are written to `$DATA_DIR/reports/<run-id>/`.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

from undead311 import duck
from undead311.coroner.join import unlabeled_templates
from undead311.paths import data_dir, worktree_root
from undead311.pipeline import run_pipeline
from undead311.stages import StageRunner

CHANNEL_REPO = "ShroudedArrow/undead-311-ops"


class Tee:
    """Write to the console and to the log file; flush every line so a killed run leaves a readable log."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> int:
        for s in self.streams:
            s.write(text)
            s.flush()
        return len(text)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def say(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


class Channel:
    """Run-log comments with a retry queue. Never raises."""

    def __init__(self, run_id: str, issue: int | None, pending: Path):
        self.run_id, self.issue, self.pending = run_id, issue, pending

    def body(self, kind: str, summary: str, evidence: str, action: str = "none") -> str:
        return (
            f"```yaml\nfrom: engine\nto: human\ntype: {kind}\nrun: {self.run_id}\n"
            f"refs: [pipeline/scripts/run_full.py, logs/{self.run_id}.log]\n```\n"
            f"**Summary** {summary}\n\n**Evidence** {evidence}\n\n**Requested action** {action}"
        )

    def post(self, body: str) -> bool:
        queue = [json.loads(line) for line in self.pending.read_text().splitlines() if line.strip()] if self.pending.exists() else []
        queue.append({"body": body})
        left: list[dict] = []
        for item in queue:
            if self.issue is None or not self._send(item["body"]):
                left.append(item)
        self.pending.parent.mkdir(parents=True, exist_ok=True)
        self.pending.write_text("".join(json.dumps(i) + "\n" for i in left))
        return not left

    def _send(self, body: str) -> bool:
        try:
            import hooklib

            hooklib.gh_request("POST", f"/repos/{CHANNEL_REPO}/issues/{self.issue}/comments", {"body": body})
            return True
        except Exception as exc:  # noqa: BLE001 - the channel never blocks a run
            say(f"[channel] comment not posted ({type(exc).__name__}); queued")
            return False


def stage_comment(rec: dict) -> tuple[str, str]:
    rows = ", ".join(f"{k} {v:,}" for k, v in rec["rows"].items()) or "none"
    summary = (
        f"Stage `{rec['stage']}` finished in {rec['seconds']:.1f} s; peak memory {rec['peak_rss_mb']:,.0f} MB "
        f"(process high-water mark {rec['process_peak_mb']:,.0f} MB)."
    )
    return summary, f"Rows: {rows}. Finished {rec['finished_utc']}."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", default="full-1")
    ap.add_argument("--issue", type=int, default=None, help="run-log issue number (default: channel.json of the run)")
    ap.add_argument("--out", type=Path, default=None, help="export folder (default $DATA_DIR/exports/<run-id>)")
    ap.add_argument("--skip-grid", action="store_true")
    ap.add_argument("--raw", type=Path, default=None, help="raw input folder (default $DATA_DIR/raw)")
    ap.add_argument("--snapshot-md", type=Path, default=None, help="SNAPSHOT.md that lists the raw files (default data/SNAPSHOT.md)")
    a = ap.parse_args(argv)

    root, base = worktree_root(), data_dir()
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_file = (logs / f"{a.run_id}.log").open("a", encoding="utf-8")
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Tee(saved[0], log_file), Tee(saved[1], log_file)
    try:
        return _run(a, root, base, logs)
    finally:
        sys.stdout, sys.stderr = saved
        log_file.close()


def _run(a: argparse.Namespace, root: Path, base: Path, logs: Path) -> int:
    stopped = logs / f"{a.run_id}.STOPPED"
    stop_file = root / ".kiro" / "STOP"
    if stop_file.exists():
        say("kill switch: .kiro/STOP exists; not starting")
        return 3
    if stopped.exists():
        say(f"{stopped.name} exists: a stage failed twice. Everything is left in place; delete the file to try again.")
        return 2

    issue = a.issue
    if issue is None:
        ch = root / ".kiro" / "workflow-runs" / a.run_id / "channel.json"
        try:
            issue = json.loads(ch.read_text()).get("issue")
        except (OSError, ValueError):
            issue = None
    channel = Channel(a.run_id, issue, logs / f"{a.run_id}.comments-pending.jsonl")

    out = a.out or base / "exports" / a.run_id
    stages_dir = logs / f"{a.run_id}.stages"
    say(f"=== {a.run_id}: branch {git(root, 'rev-parse', '--abbrev-ref', 'HEAD')} commit {git(root, 'rev-parse', '--short', 'HEAD')}")
    say(f"data dir {base}; exports {out}; stages {stages_dir}; run-log issue {issue}")
    say("duckdb settings " + json.dumps(duck.settings()))

    def on_stage(rec: dict) -> None:
        summary, evidence = stage_comment(rec)
        channel.post(channel.body("status", summary, evidence))
        if stop_file.exists():
            say("kill switch: .kiro/STOP found after a stage; stopping")
            raise SystemExit(3)

    runner = StageRunner(stages_dir, say, on_stage)
    attempts_file = logs / f"{a.run_id}.attempts.json"
    started = time.time()
    try:
        report = run_pipeline(
            out_dir=out, stages_dir=stages_dir, stage_runner=runner, grid=not a.skip_grid, log=say,
            raw_dir=a.raw, snapshot_md=a.snapshot_md, work_dir=None,
        )  # fmt: skip
    except Exception as exc:  # noqa: BLE001 - recorded, posted, then the exit code says what happened
        stage = runner.current or "unknown"
        attempts = json.loads(attempts_file.read_text()) if attempts_file.exists() else {}
        attempts[stage] = attempts.get(stage, 0) + 1
        attempts_file.write_text(json.dumps(attempts, indent=2, sort_keys=True) + "\n")
        say(f"FAILED in stage {stage} (failure {attempts[stage]} of 2): {type(exc).__name__}: {exc}")
        traceback.print_exc()
        twice = attempts[stage] >= 2
        if twice:
            stopped.write_text(f"stage {stage} failed twice at {stamp()}\n")
        channel.post(channel.body(
            "finding", f"Stage `{stage}` failed ({type(exc).__name__}: {str(exc)[:200]}), failure {attempts[stage]} of 2.",
            f"Log: {logs / (a.run_id + '.log')}. Markers for the finished stages are kept in {stages_dir}.",
            "Run stopped, nothing deleted; a human decides." if twice else "Restarting once; the run resumes after the last marker.",
        ))  # fmt: skip
        return 2 if twice else 1
    say(report.summary())
    say(f"pipeline finished in {time.time() - started:.0f} s")

    # Item 5: Coroner coverage on in-scope closed cases and the 300 most common unlabeled templates.
    rep_dir = base / "reports" / a.run_id
    rep_dir.mkdir(parents=True, exist_ok=True)
    con = duck.connect(base / "processed" / "undead311.duckdb", read_only=True)
    try:
        rows, summary = unlabeled_templates(con, root / "data" / "labels" / "coroner_labels.csv", top=300)
    finally:
        con.close()
    with (rep_dir / "unlabeled_templates_top300.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["template", "n_cases", "example_id", "systems", "example_text"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (rep_dir / "coverage.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    say(f"Coroner coverage {summary['coverage']:.2%} of {summary['closed_in_scope']:,} closed in-scope cases; "
        f"top {len(rows)} unlabeled templates cover {summary['listed_cases']:,} of {summary['unlabeled']:,} unlabeled cases")  # fmt: skip
    channel.post(channel.body(
        "done", f"Pipeline finished in {time.time() - started:.0f} s. Coroner coverage {summary['coverage']:.2%}.",
        f"Zombies {report.tier_counts}. Unlabeled: {summary['unlabeled']:,} of {summary['closed_in_scope']:,} closed in-scope cases.",
    ))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
