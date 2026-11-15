"""Nightly refresh template (ops/undead-311-data): REQ-OPS-NIGHTLY.1 to .4 and REQ-OPS-ALERT.1.

The workflow is parsed, never run. Action pinning and permissions are covered for this file by
test_workflows_pinned.py (check O1, which scans `ops/**/.github/workflows`). `status_history.py` is imported and run.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
OPS = REPO / "ops" / "undead-311-data"
NIGHTLY = OPS / ".github" / "workflows" / "nightly.yml"
HELPER = OPS / "status_history.py"

_spec = importlib.util.spec_from_file_location("status_history", HELPER)
sh = importlib.util.module_from_spec(_spec)
sys.modules["status_history"] = sh
_spec.loader.exec_module(sh)


def workflow() -> dict:
    return yaml.safe_load(NIGHTLY.read_text())


def steps() -> list[dict]:
    return workflow()["jobs"]["refresh"]["steps"]


def index(step_id: str) -> int:
    return next(i for i, s in enumerate(steps()) if s.get("id") == step_id)


def runs() -> str:
    return "\n".join(str(s.get("run", "")) for s in steps())


# ---- the workflow ---------------------------------------------------------------------------------------------------

def test_template_files_exist():
    """REQ-OPS-NIGHTLY.1: the workflow and its README are in the judged repo as a template."""
    assert NIGHTLY.exists() and (OPS / "README.md").exists()


def test_it_runs_nightly_and_by_hand():
    """REQ-OPS-NIGHTLY.1."""
    triggers = workflow().get(True, workflow().get("on"))
    assert triggers["schedule"][0]["cron"] and "workflow_dispatch" in triggers


def test_it_checks_out_the_judged_repo_at_the_frozen_tag():
    """REQ-OPS-NIGHTLY.2: the judged repo at the release tag (a repository variable), never a branch."""
    co = next(s for s in steps() if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert co["with"]["repository"] == "ShroudedArrow/undead-311"
    assert co["with"]["ref"] == "${{ vars.JUDGED_TAG }}"
    assert "JUDGED_TAG" in steps()[0]["run"] and "exit 1" in steps()[0]["run"]   # an unset tag stops the run first


def test_stages_run_in_order_and_the_deploy_comes_after_every_check():
    """REQ-OPS-NIGHTLY.2, .3: download, pipeline, status check, history merge, build, deploy. A failure never reaches the deploy."""
    order = ["checkout", "setup", "download", "pipeline", "check", "history", "build", "deploy"]
    assert [index(i) for i in order] == sorted(index(i) for i in order)
    for step_id, needle in (("download", "make data-download"), ("pipeline", "make pipeline"), ("build", "make build")):
        assert needle in steps()[index(step_id)]["run"]
    assert "status_history.py check" in steps()[index("check")]["run"]
    assert "netlify-cli@" in steps()[index("deploy")]["run"] and "--prod" in steps()[index("deploy")]["run"]
    for sid in ("download", "pipeline", "check", "build", "deploy"):
        assert not steps()[index(sid)].get("continue-on-error"), sid   # a failing stage must fail the job
        assert "if" not in steps()[index(sid)], sid


def test_deploy_ships_the_whole_site_from_the_repo_root_so_netlify_toml_applies():
    """REQ-OPS-NIGHTLY.2: web/dist (with its generated `_headers`) deployed from the judged checkout, where netlify.toml is."""
    deploy = steps()[index("deploy")]
    assert deploy["working-directory"] == "judged" and "--dir web/dist" in deploy["run"]


def test_the_cli_version_is_pinned():
    """REQ-OPS-NIGHTLY.2 (supply chain): no `@latest` and no unversioned npx package."""
    m = re.search(r"netlify-cli@(\S+)", runs())
    assert m and re.fullmatch(r"\d+\.\d+\.\d+", m.group(1))


def test_secrets_reach_only_the_steps_that_need_them():
    """REQ-OPS-NIGHTLY.2: the Netlify secrets only in the deploy step, the channel token only in the alert step."""
    job = workflow()["jobs"]["refresh"]
    assert "secrets" not in json.dumps(job.get("env", {}))
    holders = {}
    for s in steps():
        for key, value in (s.get("env") or {}).items():
            if "secrets." in str(value):
                holders.setdefault(key, []).append(s.get("id") or s.get("name"))
    assert holders == {"NETLIFY_AUTH_TOKEN": ["deploy"], "NETLIFY_SITE_ID": ["deploy"],
                       "GITHUB_CHANNEL_TOKEN": ["Open a needs-human alert in the channel"]}
    assert next(s for s in steps() if s.get("name", "").startswith("Open a needs-human"))["env"][
        "GITHUB_CHANNEL_TOKEN"] == "${{ secrets.CHANNEL_TOKEN }}"


def test_no_expression_sits_inside_a_run_script():
    """REQ-OPS-NIGHTLY.2 (injection): event and variable data goes through env vars."""
    for s in steps():
        assert "${{" not in str(s.get("run", "")), s.get("name")


def test_a_failure_keeps_the_last_deploy_records_itself_and_alerts():
    """REQ-OPS-NIGHTLY.3, REQ-OPS-ALERT.1: failure steps run only on failure, never fail the cleanup, and the job stays red."""
    record = next(s for s in steps() if s.get("name", "").startswith("Record the failure"))
    alert = next(s for s in steps() if s.get("name", "").startswith("Open a needs-human"))
    for s in (record, alert):
        assert "failure()" in s["if"] and s["continue-on-error"] is True
    assert "status_history.py record" in record["run"] and "nightly-state" in record["run"]
    assert "ci_channel.py alert" in alert["run"]
    assert steps().index(record) > index("release") and steps().index(alert) > steps().index(record)
    for stage in ("CHECKOUT", "SETUP", "DOWNLOAD", "PIPELINE", "CHECK", "BUILD", "DEPLOY", "RELEASE"):
        assert f"S_{stage}" in record["env"]


def test_the_failure_history_is_merged_before_the_build_and_cleared_only_after_the_deploy():
    """REQ-OPS-NIGHTLY.3: the next successful deploy carries the failures; they are cleared once it has shipped."""
    assert "status_history.py merge" in steps()[index("history")]["run"]
    assert index("history") < index("build") < index("deploy") < index("clear")
    assert "status_history.py clear" in steps()[index("clear")]["run"]


def test_the_release_holds_one_processed_data_file_and_its_hash():
    """REQ-OPS-NIGHTLY.4: a tar.gz of the processed folder and a SHA-256 file go to a `data-<date>` release."""
    run = steps()[index("release")]["run"]
    assert "tar -czf" in run and "processed" in run and "sha256sum" in run
    assert "gh release create" in run and "--clobber" in run and 'tag="data-$day"' in run


def test_job_permissions_are_contents_write_only():
    """REQ-OPS-NIGHTLY.4: contents: write for Releases; the alert goes out with the channel token, not an issues scope."""
    assert workflow()["jobs"]["refresh"]["permissions"] == {"contents": "write"}
    assert workflow()["permissions"] == {}


def test_the_readme_gives_the_setup_steps():
    """REQ-OPS-NIGHTLY.1: the owner can copy, set secrets and the tag variable, and run once."""
    text = (OPS / "README.md").read_text()
    for needle in ("JUDGED_TAG", "NETLIFY_AUTH_TOKEN", "NETLIFY_SITE_ID", "CHANNEL_TOKEN", "GITHUB_CHANNEL_TOKEN",
                   "undead-311-data", "nightly-state", "data-YYYY-MM-DD", "docs/DEPLOY.md", "needs-human"):
        assert needle in text, needle
    assert not re.search(r"\b(ghp_|github_pat_|nfp_)[A-Za-z0-9_]{10,}", text)


# ---- status_history.py ----------------------------------------------------------------------------------------------

def test_the_first_failed_stage_in_pipeline_order_is_named():
    """REQ-OPS-NIGHTLY.3."""
    assert sh.failed_stage({"download": "success", "pipeline": "failure", "build": "skipped"}) == "pipeline"
    assert sh.failed_stage({"pipeline": "cancelled", "deploy": "failure"}) == "pipeline"
    assert sh.failed_stage({"download": "success", "deploy": "skipped"}) == "unknown"
    assert sh.failed_stage({"checkout": "", "setup": ""}) == "unknown"          # steps that never ran have an empty outcome


def test_record_appends_a_failure_entry_and_keeps_only_the_newest_ten():
    """REQ-OPS-NIGHTLY.3: bounded history; the entry holds a time, a stage and a run URL, nothing else."""
    history: list[dict] = []
    for n in range(14):
        history = sh.record(history, "pipeline", f"https://x/{n}", f"2026-12-{n + 1:02d}T03:41:00Z")
    assert len(history) == sh.KEEP and history[0]["run_url"] == "https://x/4" and history[-1]["run_url"] == "https://x/13"
    assert set(history[-1]) == {"at", "ok", "stage", "run_url"} and history[-1]["ok"] is False


def test_merge_puts_history_in_status_without_changing_the_rest():
    """REQ-OPS-NIGHTLY.3: a good run's status.json gains `history` and keeps `ok: true`."""
    status = {"ok": True, "data_version": "d", "row_counts": {"cases": 1}}
    out = sh.merge(status, [{"at": "t", "ok": False, "stage": "build", "run_url": "u"}])
    assert out["ok"] is True and out["history"][0]["stage"] == "build"
    assert {k: v for k, v in out.items() if k != "history"} == status and "history" not in status


def test_the_status_schema_accepts_the_merged_history():
    """REQ-OPS-NIGHTLY.3: status.json with `history` still validates (additionalProperties is true)."""
    import jsonschema

    schema = json.loads((REPO / "schemas" / "status.schema.json").read_text())
    status = json.loads((REPO / "web" / "public" / "data" / "status.json").read_text())
    jsonschema.validate(sh.merge(status, [{"at": "t", "ok": False, "stage": "build", "run_url": "u"}]), schema)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, check=False, timeout=60)


def test_check_passes_only_for_an_ok_status(tmp_path):
    """REQ-OPS-NIGHTLY.3: a missing, damaged, failed or non-boolean status stops the run before the deploy."""
    p = tmp_path / "status.json"
    assert run_cli("check", "--status", str(p)).returncode == 1               # missing
    p.write_text("{not json")
    assert run_cli("check", "--status", str(p)).returncode == 1               # damaged
    for bad in ('{"ok": false}', '{"ok": "true"}', "[]", "{}"):
        p.write_text(bad)
        assert run_cli("check", "--status", str(p)).returncode == 1, bad
    p.write_text('{"ok": true}')
    assert run_cli("check", "--status", str(p)).returncode == 0


def test_the_cli_round_trip_record_merge_clear(tmp_path):
    """REQ-OPS-NIGHTLY.3: a failed night is recorded, shows up in the next good status, and is cleared after the deploy."""
    hist, status = tmp_path / "failure-history.json", tmp_path / "status.json"
    status.write_text('{"ok": true, "data_version": "v"}')
    r = run_cli("record", "--history", str(hist), "--run-url", "https://x/1", "--at", "2026-12-01T03:41:00Z",
                "--outcomes", "download=success", "pipeline=failure", "build=skipped")
    assert r.returncode == 0
    assert json.loads(hist.read_text())[0]["stage"] == "pipeline"
    assert run_cli("merge", "--status", str(status), "--history", str(hist)).returncode == 0
    assert json.loads(status.read_text())["history"][0]["run_url"] == "https://x/1"
    assert run_cli("clear", "--history", str(hist)).returncode == 0
    assert json.loads(hist.read_text()) == []
    assert run_cli("merge", "--status", str(status), "--history", str(hist)).returncode == 0
    assert json.loads(status.read_text())["history"] == []


@pytest.mark.parametrize("content", ["", "{broken", '{"a": 1}', '["x", 3, {"stage": "build"}]'])
def test_a_damaged_history_file_never_breaks_the_run(tmp_path, content):
    """REQ-OPS-NIGHTLY.3: a bad history asset is treated as empty, not as a failure of the night."""
    hist = tmp_path / "failure-history.json"
    hist.write_text(content)
    assert run_cli("record", "--history", str(hist), "--outcomes", "build=failure").returncode == 0
    entries = json.loads(hist.read_text())
    assert entries[-1]["stage"] == "build" and all(isinstance(e, dict) for e in entries)
