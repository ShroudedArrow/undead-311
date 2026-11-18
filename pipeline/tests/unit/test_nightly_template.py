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
    """REQ-OPS-NIGHTLY.2, .3, REQ-OPS-PUBLISH.3: download the exports, unpack, status check, history merge, build, deploy.
    A failure never reaches the deploy, and the pipeline itself no longer runs here."""
    order = ["tag", "checkout", "setup", "freeze", "download", "exports", "check", "history", "build", "verify", "trim", "draft", "smoke", "deploy"]
    assert [index(i) for i in order] == sorted(index(i) for i in order)
    for step_id, needle in (("download", "exports_release.py latest"), ("exports", "exports_release.py unpack"), ("build", "make build")):
        assert needle in steps()[index(step_id)]["run"]
    assert "make pipeline" not in runs() and "make data-download" not in runs()
    assert "status_history.py check" in steps()[index("check")]["run"]
    assert "netlify-cli@" in steps()[index("deploy")]["run"] and "--prod" in steps()[index("deploy")]["run"]
    for sid in ("download", "exports", "check", "build", "draft", "smoke", "deploy"):
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
    assert holders == {"NETLIFY_AUTH_TOKEN": ["draft", "deploy"], "NETLIFY_SITE_ID": ["draft", "deploy"],
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
    assert steps().index(record) > index("clear") and steps().index(alert) > steps().index(record)
    for stage in ("TAG", "CHECKOUT", "SETUP", "FREEZE", "DOWNLOAD", "EXPORTS", "CHECK", "HISTORY", "BUILD", "VERIFY",
                  "TRIM", "DRAFT", "SMOKE", "DEPLOY", "CLEAR"):
        assert f"S_{stage}" in record["env"]


def test_the_failure_history_is_merged_before_the_build_and_cleared_only_after_the_deploy():
    """REQ-OPS-NIGHTLY.3: the next successful deploy carries the failures; they are cleared once it has shipped."""
    assert "status_history.py merge" in steps()[index("history")]["run"]
    assert index("history") < index("build") < index("deploy") < index("clear")
    assert "status_history.py clear" in steps()[index("clear")]["run"]


def test_judge_mode_files_are_frozen_before_the_pipeline_and_verified_before_the_deploy():
    """REQ-OPS-SNAP.2 (ops#157): the copy is taken from the tag before the unpacked exports rewrite the data, and the built
    site is checked against data/SNAPSHOT.md before it ships. Neither step may be skipped or allowed to fail quietly."""
    freeze, verify = steps()[index("freeze")], steps()[index("verify")]
    assert "snapshot.py --freeze-judge" in freeze["run"] and index("freeze") < index("exports")
    assert "snapshot.py --check-frozen --public web/dist/data" in verify["run"] and index("build") < index("verify") < index("deploy")
    for s in (freeze, verify):
        assert s["working-directory"] == "judged" and not s.get("continue-on-error") and "if" not in s


def test_the_exports_come_from_a_release_asset_of_the_data_repo_with_the_jobs_own_token():
    """REQ-OPS-PUBLISH.3: the newest `exports-*` release is downloaded with github.token (no extra secret), then verified."""
    download = steps()[index("download")]
    assert download["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "gh release download" in download["run"] and '--repo "$DATA_REPO"' in download["run"]
    assert "exports-*.tar.gz" in download["run"] and "exports-*.sha256" in download["run"]
    unpack = steps()[index("exports")]
    assert "--sha256" in unpack["run"] and "--dest web/public/data" in unpack["run"] and unpack["working-directory"] == "judged"


def test_job_permissions_are_contents_write_only():
    """REQ-OPS-NIGHTLY.4: contents: write for Releases; the alert goes out with the channel token, not an issues scope."""
    assert workflow()["jobs"]["refresh"]["permissions"] == {"contents": "write"}
    assert workflow()["permissions"] == {}


def test_the_readme_gives_the_setup_steps():
    """REQ-OPS-NIGHTLY.1: the owner can copy, set secrets and the tag variable, and run once."""
    text = (OPS / "README.md").read_text()
    for needle in ("JUDGED_TAG", "NETLIFY_AUTH_TOKEN", "NETLIFY_SITE_ID", "CHANNEL_TOKEN", "GITHUB_CHANNEL_TOKEN",
                   "undead-311-data", "nightly-state", "exports-", "exports_release.py", "DATA_RELEASE_TOKEN", "docs/DEPLOY.md", "needs-human"):
        assert needle in text, needle
    assert not re.search(r"\b(ghp_|github_pat_|nfp_)[A-Za-z0-9_]{10,}", text)


# ---- status_history.py ----------------------------------------------------------------------------------------------

def test_the_first_failed_stage_in_pipeline_order_is_named():
    """REQ-OPS-NIGHTLY.3."""
    assert sh.failed_stage({"download": "success", "exports": "failure", "build": "skipped"}) == "exports"
    assert sh.failed_stage({"exports": "cancelled", "deploy": "failure"}) == "exports"
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
    """REQ-OPS-NIGHTLY.3: status.json with `history` validates, and the schema defines the entry (ops#159)."""
    import jsonschema

    schema = json.loads((REPO / "schemas" / "status.schema.json").read_text())
    status = json.loads((REPO / "web" / "public" / "data" / "status.json").read_text())
    entry = {"at": "2026-12-01T03:41:00Z", "ok": False, "stage": "build", "run_url": "u"}
    jsonschema.validate(sh.merge(status, [entry]), schema)
    assert set(schema["properties"]["history"]["items"]["required"]) == {"at", "ok", "stage", "run_url"}
    for broken in ({**entry, "ok": True}, {**entry, "stage": 3}, {k: v for k, v in entry.items() if k != "at"},
                   {**entry, "name": "someone"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**status, "history": [broken]}, schema)


def test_every_workflow_step_id_is_a_named_stage():
    """REQ-OPS-NIGHTLY.3 (ops#158): a failure in any step with an id is recorded under its name, never `unknown`."""
    ids = [s["id"] for s in steps() if s.get("id")]
    assert set(ids) <= set(sh.STAGES), set(ids) - set(sh.STAGES)
    assert [i for i in sh.STAGES if i in ids] == ids              # same order as the workflow runs them
    record = next(s for s in steps() if s.get("name", "").startswith("Record the failure"))
    assert all(f"{i}=$S_{i.upper()}" in record["run"] and f"steps.{i}.outcome" in record["env"][f"S_{i.upper()}"] for i in ids)


@pytest.mark.parametrize("stage", sh.STAGES)
def test_each_stage_failing_is_named(stage):
    """REQ-OPS-NIGHTLY.3 (ops#158): setup and history failures are named like the rest."""
    outcomes = {s: "success" for s in sh.STAGES}
    outcomes[stage] = "failure"
    assert sh.failed_stage(outcomes) == stage


def test_the_history_step_validates_against_the_status_schema():
    """REQ-OPS-NIGHTLY.3 (ops#159): the merge runs where jsonschema is installed and passes the schema."""
    step = steps()[index("history")]
    assert "uv run --locked python ops/undead-311-data/status_history.py merge" in step["run"]
    assert "--schema schemas/status.schema.json" in step["run"] and step["working-directory"] == "judged"


def test_merge_with_a_schema_refuses_a_status_that_would_break_it(tmp_path):
    """REQ-OPS-NIGHTLY.3 (ops#159): a merge that does not validate fails and leaves status.json as it was."""
    schema = REPO / "schemas" / "status.schema.json"
    good = json.loads((REPO / "web" / "public" / "data" / "status.json").read_text())
    status, hist = tmp_path / "status.json", tmp_path / "h.json"
    status.write_text(json.dumps(good))
    hist.write_text(json.dumps([{"at": "2026-12-01T03:41:00Z", "ok": False, "stage": "setup", "run_url": "u"}]))
    assert run_cli("merge", "--status", str(status), "--history", str(hist), "--schema", str(schema)).returncode == 0
    assert json.loads(status.read_text())["history"][0]["stage"] == "setup"
    bad = {**good, "ok": "yes"}                                   # the pipeline's own fields break the schema
    status.write_text(json.dumps(bad))
    r = run_cli("merge", "--status", str(status), "--history", str(hist), "--schema", str(schema))
    assert r.returncode == 1 and "status.schema.json" in r.stderr and json.loads(status.read_text()) == bad


def test_a_history_entry_the_schema_would_reject_is_dropped_on_load(tmp_path):
    """REQ-OPS-NIGHTLY.3: extra keys, a true `ok` or a non-string field never reach status.json."""
    ok = {"at": "t", "ok": False, "stage": "build", "run_url": "u"}
    hist = tmp_path / "h.json"
    hist.write_text(json.dumps([ok, {**ok, "ok": True}, {**ok, "stage": 1}, {**ok, "extra": 1}, {"stage": "build"}]))
    assert sh.load_history(hist) == [ok]


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
                "--outcomes", "download=success", "exports=failure", "build=skipped")
    assert r.returncode == 0
    assert json.loads(hist.read_text())[0]["stage"] == "exports"
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


def test_the_nightly_build_installs_a_browser_and_requires_share_images():
    """REQ-WEB-LINKS.2 (UX-39): the nightly build draws the share images or fails; it never ships without them."""
    build = steps()[index("build")]
    assert build["run"].index("playwright install") < build["run"].index("make build")
    assert build["env"]["SHARE_IMAGES"] == "required"


# ---- repo scripts run through uv, from the judged checkout (the duckdb ModuleNotFoundError) ---------------------------

def run_lines() -> list[tuple[str, str]]:
    """(step name, command line) for every non-blank, non-comment line of every `run:` script."""
    out = []
    for s in steps():
        for line in str(s.get("run", "")).splitlines():
            if line.strip() and not line.strip().startswith("#"):
                out.append((s.get("name", s.get("id", "?")), line.strip()))
    return out


def test_no_step_calls_bare_python_for_a_repo_script():
    """REQ-OPS-NIGHTLY.2: the runner's own python has none of the judged checkout's dependencies (duckdb, jsonschema), so
    `python3 pipeline/scripts/snapshot.py` failed with ModuleNotFoundError. Every `.py` in a run script goes through
    `uv run --locked python`, and no command line starts a bare `python` or `python3`."""
    bare = re.compile(r"(^|[\s;&|(`$])python3?(\s|$)")
    repo_script = re.compile(r"[\w./-]+\.py\b")
    seen = 0
    for name, line in run_lines():
        if repo_script.search(line):
            seen += 1
            assert "uv run --locked python " in line, f"{name}: {line}"
        stripped = line.replace("uv run --locked python ", "uv-run-python ")
        assert not bare.search(stripped), f"{name}: bare python in: {line}"
    assert seen >= 8                                  # freeze, latest, unpack, check, merge, verify, clear, record, alert


def test_every_script_runs_from_the_judged_checkout_and_exists_there():
    """REQ-OPS-NIGHTLY.2: `uv run` finds the project (pyproject.toml, uv.lock) from the working directory, so each step that
    runs a repo script sets `working-directory: judged`, and the script path is relative to it and exists in the repo."""
    for s in steps():
        text = str(s.get("run", ""))
        scripts = re.findall(r"uv run --locked python (\S+\.py)", text)
        if not scripts:
            continue
        assert s.get("working-directory") == "judged", s.get("name")
        for script in scripts:
            assert not script.startswith(("judged/", "/")), f"{script} is relative to the judged checkout"
            assert (REPO / script).is_file(), f"{script} does not exist in the repo"


def test_uv_is_set_up_and_the_dependencies_are_installed_locked_before_any_script_runs():
    """REQ-OPS-NIGHTLY.2: setup-uv, then `uv sync --locked` and `npm ci` (not the unlocked `make setup`), then the first
    `uv run`. The scripts at a tag need nothing the tag does not already have."""
    uses = [s.get("uses", "") for s in steps()]
    uv_at = next(i for i, u in enumerate(uses) if u.startswith("astral-sh/setup-uv@"))
    setup = steps()[index("setup")]
    assert "uv sync --locked" in setup["run"] and "npm --prefix web ci" in setup["run"] and "make setup" not in runs()
    first_run = next(i for i, s in enumerate(steps()) if "uv run" in str(s.get("run", "")))
    assert uv_at < index("setup") < first_run
    assert all("uv run" not in str(s.get("run", "")) or "uv run --locked" in str(s.get("run", "")) for s in steps())
    assert "uv run python" not in runs()


def test_actions_are_on_node_24_majors():
    """REQ-OPS-NIGHTLY.2: checkout and setup-node v5+ and setup-uv v7+ run on Node 24 (their action.yml says `node24`);
    v4 and setup-uv v5 and v6 still run on Node 20, which GitHub is retiring and warns about."""
    minimum = {"actions/checkout": 5, "actions/setup-node": 5, "astral-sh/setup-uv": 7}
    found = {}
    for s in steps():
        uses = str(s.get("uses", ""))
        if "@" in uses:
            action, ref = uses.split("@", 1)
            found[action] = int(re.match(r"v(\d+)", ref).group(1))
    assert set(found) == set(minimum)
    for action, major in found.items():
        assert major >= minimum[action], f"{action}@v{major} runs on Node 20"


# ---- deploy: draft, smoke test, production (REQ-OPS-NIGHTLY.5) -------------------------------------------------------------

def netlify_commands() -> list[str]:
    return [line for line in runs().splitlines() if "netlify-cli@" in line]


def test_every_netlify_deploy_skips_the_build_because_the_job_already_built_the_site():
    """REQ-OPS-NIGHTLY.5: without --no-build the CLI ran the project's build again (15 minutes, every share image)."""
    commands = netlify_commands()
    assert len(commands) == 2
    for c in commands:
        assert " deploy " in c and "--no-build" in c and "--dir web/dist" in c, c
    assert not any("--build" in c.replace("--no-build", "") for c in commands)


def test_the_first_deploy_is_a_draft_the_second_is_production_and_only_the_second_says_prod():
    """REQ-OPS-NIGHTLY.5: a draft has no --prod and prints its URL as JSON; production has --prod."""
    draft, prod = steps()[index("draft")], steps()[index("deploy")]
    assert "--prod" not in draft["run"] and "--json" in draft["run"] and "deploy_url" in draft["run"]
    assert "--prod" in prod["run"]
    assert "GITHUB_OUTPUT" in draft["run"] and "url=" in draft["run"]


def test_the_smoke_test_runs_on_the_draft_between_the_two_deploys_and_blocks_production():
    """REQ-OPS-NIGHTLY.5: draft, then smoke test, then production; the smoke step cannot be skipped or allowed to fail."""
    assert index("verify") < index("trim") < index("draft") < index("smoke") < index("deploy") < index("clear")
    smoke = steps()[index("smoke")]
    assert "uv run --locked python ops/undead-311-data/smoke_test.py" in smoke["run"]
    assert smoke["env"]["DRAFT_URL"] == "${{ steps.draft.outputs.url }}" and '--base-url "$DRAFT_URL"' in smoke["run"]
    assert "--archive" in smoke["run"] and "exports-*.tar.gz" in smoke["run"] and "--judging data/judging" in smoke["run"]
    for sid in ("draft", "smoke", "deploy"):
        s = steps()[index(sid)]
        assert not s.get("continue-on-error") and "if" not in s and s["working-directory"] == "judged", sid
    assert "--allow-excess" not in smoke["run"] and "--strict-at" not in smoke["run"]


def test_the_deploy_steps_have_a_60_minute_limit_and_the_job_limit_leaves_room_for_them():
    """REQ-OPS-NIGHTLY.5: timeout-minutes: 60 on the draft and production deploys; the job limit is higher than one of them."""
    assert steps()[index("draft")]["timeout-minutes"] == 60 and steps()[index("deploy")]["timeout-minutes"] == 60
    assert 0 < steps()[index("smoke")]["timeout-minutes"] <= 15
    assert workflow()["jobs"]["refresh"]["timeout-minutes"] > 60


def test_a_manual_run_and_the_scheduled_run_never_overlap():
    """REQ-OPS-NIGHTLY.5: one concurrency group for the workflow; a running deploy is never cancelled by a newer run."""
    c = workflow()["concurrency"]
    assert c["group"] == "nightly" and c["cancel-in-progress"] is False
    assert "concurrency" not in workflow()["jobs"]["refresh"]        # a second group on the job would let the two runs overlap again


def test_a_failed_smoke_test_alerts_with_the_draft_and_production_is_not_reached():
    """REQ-OPS-NIGHTLY.5, REQ-OPS-ALERT.1: the alert step runs on failure and names the draft when the smoke test is what failed."""
    alert = next(s for s in steps() if s.get("name", "").startswith("Open a needs-human"))
    assert "failure()" in alert["if"] and alert["env"]["S_SMOKE"] == "${{ steps.smoke.outcome }}"
    assert alert["env"]["DRAFT_URL"] == "${{ steps.draft.outputs.url }}" and "smoke test failed" in alert["run"]
    assert steps().index(alert) > index("clear")


def test_the_build_step_passes_the_optional_site_url_for_absolute_share_image_addresses():
    """REQ-WEB-LINKS.2: SITE_URL comes from a repository variable (an empty value keeps the addresses relative)."""
    assert steps()[index("build")]["env"]["SITE_URL"] == "${{ vars.SITE_URL }}"


def test_the_smoke_test_script_exists_in_the_repo_the_template_runs_it_from():
    """REQ-OPS-NIGHTLY.5: the path in the workflow is a real file (a tag cut before it existed would fail the step, not skip it)."""
    assert (OPS / "smoke_test.py").is_file()


# ---- files left out of the deploy -------------------------------------------------------------------------------------

_spec2 = importlib.util.spec_from_file_location("smoke_test", OPS / "smoke_test.py")
smoke = importlib.util.module_from_spec(_spec2)
sys.modules.setdefault("smoke_test", smoke)
_spec2.loader.exec_module(smoke)


def test_the_trim_step_runs_after_the_build_and_before_the_draft_and_leaves_out_exactly_the_smoke_test_lists():
    """REQ-OPS-NIGHTLY.5: the deleted paths are the ones the smoke test expects to be absent, and nothing else."""
    step = steps()[index("trim")]
    assert index("build") < index("trim") < index("draft")
    assert step["working-directory"] == "judged" and not step.get("continue-on-error") and "if" not in step
    named = set(re.findall(r"web/dist/([\w./-]+)", step["run"]))
    assert named == set(smoke.LEFT_OUT_DIRS) | set(smoke.LEFT_OUT_FILES)


def test_running_the_trim_step_deletes_only_those_files(tmp_path):
    """REQ-OPS-NIGHTLY.5: the step's own shell text, run on a small copy of web/dist."""
    dist = tmp_path / "web" / "dist"
    keep = ["index.html", "data/status.json", "data/points.json", "data/stats/scorecard.json", "data/stats/judge_tour.json",
            "data/cards/back-bay-2020.json", "data/zombies/index.json", "data/frozen/points.json", "share/site.png"]
    gone = ["data/incidents/back-bay-2020.json", "data/incidents/dorchester-2021.json", "data/separate_deaths.json",
            "data/stats/trends.json", "data/stats/stats_status.json"]
    for rel in keep + gone:
        f = dist / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    script = steps()[index("trim")]["run"]
    result = subprocess.run(["sh", "-ec", script], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert all((dist / rel).exists() for rel in keep)
    assert not any((dist / rel).exists() for rel in gone) and not (dist / "data" / "incidents").exists()
    # a second run on the already trimmed folder succeeds (a re-run of the job)
    assert subprocess.run(["sh", "-ec", script], cwd=tmp_path, check=False).returncode == 0


def test_no_page_of_the_app_fetches_the_files_that_are_left_out():
    """REQ-OPS-NIGHTLY.5: the app's source never names these files as data to load (the parser registry names them only as
    schema validators), so deleting them cannot break a page."""
    src = REPO / "web" / "src"
    names = ("separate_deaths.json", "trends.json", "stats_status.json", "incidents/")
    offenders = []
    for f in src.rglob("*.ts*"):
        rel = f.relative_to(src).as_posix()
        if rel.startswith("lib/parse/generated") or ".test." in rel:
            continue
        text = f.read_text()
        offenders += [f"{rel}: {n}" for n in names if n in text]
    assert offenders == []
    from_stats = (src / "lib" / "statsFiles.ts").read_text()
    assert "trends" not in from_stats and "stats_status" not in from_stats
