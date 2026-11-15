"""Check O1 (nightly-and-deploy design): every workflow pins its actions and sets least-privilege permissions.

REQ-OPS-CI.4: every `uses:` is pinned to a tagged version (or a full commit SHA) and every job declares `permissions:`.
REQ-OPS-CI.1: `.github/workflows/ci.yml` has the `python` and `web` jobs with the checks the requirement names.
The scan covers `.github/workflows/*.yml` and the data-repo template under `ops/**/.github/workflows/`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted(
    [*(REPO / ".github" / "workflows").glob("*.y*ml"), *(REPO / "ops").glob("**/.github/workflows/*.y*ml")]
)

# v4, v4.2.1, 1.2.3, v2.0.0-beta.1. A suffix must be a semver pre-release (alpha, beta, rc, pre), so branch-style
# refs such as v4.x, 1.x, v2-dev and v1-branch do not pass (review N3, ops#55).
TAG_REF = re.compile(r"^v?\d+(\.\d+){0,2}(-(alpha|beta|rc|pre)([.-]?\d+)*)?$")
SHA_REF = re.compile(r"^[0-9a-f]{40}$")
# Job-level write scopes allowed per workflow location. CI jobs never write; the data-repo template (ops/) needs
# `contents: write` for the Release with the Parquet files and `issues: write` for the needs-human alert.
WRITE_ALLOWED = {"ci": set(), "ops": {"contents", "issues"}}


def unpinned(uses: str) -> str | None:
    """Why a `uses:` value is not pinned, or None when it is. Local actions (./path) are part of the repo."""
    if uses.startswith("./"):
        return None
    if uses.startswith("docker://"):
        return None if "@sha256:" in uses else "docker image without a digest"
    if "@" not in uses:
        return "no @ref"
    ref = uses.rsplit("@", 1)[1]
    if TAG_REF.match(ref) or SHA_REF.match(ref):
        return None
    return f"ref {ref!r} is a branch or moving name, not a tag or SHA"


def used_actions(doc: dict) -> list[str]:
    """Every `uses:` in the workflow's jobs: step-level actions and reusable workflows."""
    found: list[str] = []
    for job in (doc.get("jobs") or {}).values():
        if "uses" in job:
            found.append(job["uses"])
        found.extend(s["uses"] for s in job.get("steps", []) if "uses" in s)
    return found


def jobs_without_permissions(doc: dict) -> list[str]:
    return [name for name, job in (doc.get("jobs") or {}).items() if "permissions" not in job]


def excess_permissions(doc: dict, allowed: set[str]) -> list[str]:
    """Permissions broader than least privilege (REQ-OPS-CI.4, review N3): `write-all` anywhere, any write scope
    at workflow level, and any job-level write scope that is not in `allowed`."""
    bad: list[str] = []

    def scan(where: str, perms, allow: set[str]) -> None:
        if perms is None:
            return
        if isinstance(perms, str):
            if perms == "write-all":
                bad.append(f"{where}: write-all")
            return
        bad.extend(f"{where}: {scope}: write" for scope, level in perms.items()
                   if level == "write" and scope not in allow)

    scan("workflow", doc.get("permissions"), set())
    for name, job in (doc.get("jobs") or {}).items():
        scan(f"job {name}", job.get("permissions"), allowed)
    return bad


def location(path: Path) -> str:
    return "ops" if "ops" in path.relative_to(REPO).parts[:1] else "ci"


def load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text())
    assert isinstance(doc, dict), path
    return doc


def test_there_is_a_workflow_to_check():
    """REQ-OPS-CI.1: the scan is not vacuous."""
    assert REPO / ".github" / "workflows" / "ci.yml" in WORKFLOWS


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: str(p.relative_to(REPO)))
def test_every_action_is_pinned_and_every_job_has_permissions(path):
    """REQ-OPS-CI.4 (check O1)."""
    doc = load(path)
    assert (doc.get("jobs") or {}), f"{path.name} has no jobs"
    bad = {u: why for u in used_actions(doc) if (why := unpinned(u))}
    assert not bad, f"{path.name}: unpinned actions {bad}"
    assert not jobs_without_permissions(doc), f"{path.name}: jobs without permissions: {jobs_without_permissions(doc)}"
    assert not excess_permissions(doc, WRITE_ALLOWED[location(path)]), excess_permissions(doc, WRITE_ALLOWED[location(path)])


@pytest.mark.parametrize(
    "uses",
    ["actions/checkout", "actions/checkout@main", "actions/checkout@master", "owner/repo@feature-x",
     "owner/repo@abc123", "docker://node:22", "a/b@v4.x", "a/b@1.x", "a/b@v2-dev", "a/b@v1-branch",
     "a/b@v4.2.1.x"],
)
def test_the_pin_check_rejects_moving_refs(uses):
    """REQ-OPS-CI.4: the O1 checker bites. Branches, short SHAs, bare names and untagged images fail."""
    assert unpinned(uses)


@pytest.mark.parametrize(
    "uses",
    ["actions/checkout@v4", "actions/setup-node@v4.1.0", "astral-sh/setup-uv@v5", "./local-action",
     "a/b@v2.0.0-beta.1", "a/b@1.2.3-rc1", "actions/checkout@" + "a" * 40, "docker://node@sha256:" + "b" * 64],
)
def test_the_pin_check_accepts_tags_and_full_shas(uses):
    """REQ-OPS-CI.4."""
    assert unpinned(uses) is None


def test_a_job_without_permissions_is_reported():
    """REQ-OPS-CI.4: the O1 checker bites on permissions too."""
    doc = {"jobs": {"a": {"permissions": {"contents": "read"}, "steps": []}, "b": {"steps": []}}}
    assert jobs_without_permissions(doc) == ["b"]


def test_ci_runs_the_checks_the_requirement_names():
    """REQ-OPS-CI.1: pull requests run make setup, make test (golden check), schema validation, ruff and tsc/vitest."""
    doc = load(REPO / ".github" / "workflows" / "ci.yml")
    triggers = doc.get(True, doc.get("on"))   # YAML 1.1 reads the key `on` as True
    assert "pull_request" in triggers
    assert {"python", "web"} <= set(doc["jobs"])
    py = "\n".join(s.get("run", "") for s in doc["jobs"]["python"]["steps"])
    for cmd in ("make setup", "make test", "make schema-check", "ruff check"):
        assert cmd in py, cmd
    web = "\n".join(s.get("run", "") for s in doc["jobs"]["web"]["steps"])
    for cmd in ("npm ci", "tsc --noEmit", "npm test"):
        assert cmd in web, cmd


def test_ci_jobs_hold_read_only_contents_permission():
    """REQ-OPS-CI.4: least privilege. Neither core job can write to the repo."""
    doc = load(REPO / ".github" / "workflows" / "ci.yml")
    for name in ("python", "web"):
        assert doc["jobs"][name]["permissions"] == {"contents": "read"}, name


def test_excess_permissions_are_reported():
    """REQ-OPS-CI.4 (review N3): write-all, workflow-level writes and job writes off the allow list are rejected."""
    assert excess_permissions({"permissions": "write-all", "jobs": {}}, set())
    assert excess_permissions({"permissions": {"contents": "write"}, "jobs": {}}, {"contents"})
    assert excess_permissions({"jobs": {"a": {"permissions": "write-all"}}}, {"contents"})
    assert excess_permissions({"jobs": {"a": {"permissions": {"contents": "write"}}}}, set())
    assert not excess_permissions({"jobs": {"a": {"permissions": {"contents": "read", "issues": "write"}}}}, {"issues"})
    assert not excess_permissions({"permissions": {}, "jobs": {"a": {"permissions": {"contents": "read"}}}}, set())


def test_ci_creates_the_uv_cache_folder_before_setup():
    """REQ-OPS-CI.1 (review N5): UV_CACHE_DIR exists before `make setup`, so the Makefile's fallback keeps it."""
    steps = load(REPO / ".github" / "workflows" / "ci.yml")["jobs"]["python"]["steps"]
    runs = [s.get("run", "") for s in steps]
    mk = next(i for i, r in enumerate(runs) if "mkdir -p" in r and "UV_CACHE_DIR" in r)
    setup = next(i for i, r in enumerate(runs) if "make setup" in r)
    cache = next(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("astral-sh/setup-uv"))
    assert cache < mk < setup


# ---- credibility layer: the jobs REQ-OPS-CI.2 and REQ-OPS-CI.3 add ------------------------------------------------

def ci_jobs() -> dict:
    return load(REPO / ".github" / "workflows" / "ci.yml")["jobs"]


def job_text(job: dict) -> str:
    return "\n".join(str(s.get("run", "")) for s in job["steps"])


def test_ci_runs_the_credibility_checks():
    """REQ-OPS-CI.2: copy-lint, an axe scan of judge mode, the bundle budget, pip-audit and npm audit."""
    jobs = ci_jobs()
    assert {"copy-lint", "axe", "budget", "audit", "channel"} <= set(jobs)
    assert "make copy-lint" in job_text(jobs["copy-lint"])
    axe = job_text(jobs["axe"])
    assert "playwright test e2e/a11y.spec.ts" in axe and "playwright install" in axe
    assert "make build" in job_text(jobs["budget"])
    audit = job_text(jobs["audit"])
    assert "pip-audit" in audit and "npm audit --audit-level=high" in audit


def test_the_budget_job_runs_the_strict_first_view_check():
    """REQ-OPS-CI.2: `make build` ends with check-build.mjs --strict, the 3 MB first-view gate."""
    pkg = (REPO / "web" / "package.json").read_text()
    assert "check-build.mjs --strict" in pkg
    assert "BUDGET_BYTES = 3 * 1024 * 1024" in (REPO / "web" / "scripts" / "check-build.mjs").read_text()


def test_the_axe_spec_scans_judge_mode():
    """REQ-OPS-CI.2: the spec the axe job runs covers /judge and fails only on serious or critical violations."""
    spec = (REPO / "web" / "e2e" / "a11y.spec.ts").read_text()
    assert 'page.goto("/judge")' in spec and '"serious"' in spec and '"critical"' in spec


def test_the_channel_job_posts_after_everything_and_cannot_fail_the_build():
    """REQ-OPS-CI.3: runs always, after every check, maps CHANNEL_TOKEN, and its post step is fail-open."""
    ci = load(REPO / ".github" / "workflows" / "ci.yml")
    job = ci["jobs"]["channel"]
    assert set(job["needs"]) == set(ci["jobs"]) - {"channel"}
    assert "always()" in str(job["if"])
    assert job["env"]["GITHUB_CHANNEL_TOKEN"] == "${{ secrets.CHANNEL_TOKEN }}"
    post = next(s for s in job["steps"] if "ci_channel.py" in str(s.get("run", "")))
    assert post.get("continue-on-error") is True
    assert job["permissions"] == {"contents": "read"}


def test_event_data_reaches_the_channel_script_through_env_not_shell_text():
    """REQ-OPS-CI.3 (injection): no `${{ ... }}` expression sits inside a run script, so a branch name cannot inject."""
    for name, job in ci_jobs().items():
        for step in job["steps"]:
            assert "${{" not in str(step.get("run", "")), f"{name}: expression inside run: {step['run']!r}"


def test_the_ci_checks_have_no_continue_on_error():
    """REQ-OPS-CI.2: a check that cannot fail the build is not a check. Only the channel post is fail-open."""
    for name, job in ci_jobs().items():
        for step in job["steps"]:
            if name != "channel":
                assert not step.get("continue-on-error"), f"{name}: {step.get('name')}"


# ---- deep property tests (REQ-OPS-PBT) ------------------------------------------------------------------------------

DEEP = REPO / ".github" / "workflows" / "deep-pbt.yml"


def test_deep_pbt_runs_nightly_with_the_deep_profile_and_a_cached_example_database():
    """REQ-OPS-PBT.1: nightly schedule, HYPOTHESIS_PROFILE=deep, `.hypothesis` cached with actions/cache."""
    doc = load(DEEP)
    triggers = doc.get(True, doc.get("on"))
    assert triggers["schedule"] and "workflow_dispatch" in triggers
    py = doc["jobs"]["python"]
    assert py["env"]["HYPOTHESIS_PROFILE"] == "deep"
    cache = next(s for s in py["steps"] if str(s.get("uses", "")).startswith("actions/cache@"))
    assert cache["with"]["path"] == ".hypothesis"
    assert "restore-keys" in cache["with"]            # a new night starts from the last night's database


def test_the_deep_profile_is_ten_times_the_fast_profile_and_stores_its_database_under_dot_hypothesis():
    """REQ-OPS-PBT.1: 10x examples, and the database folder is the one the workflow caches."""
    from hypothesis import settings

    fast, deep = settings.get_profile("fast"), settings.get_profile("deep")
    assert deep.max_examples == 10 * fast.max_examples
    assert str(deep.database.path).replace("\\", "/").startswith(".hypothesis")


def test_deep_pbt_runs_fast_check_ten_times_through_a_separate_vitest_config():
    """REQ-OPS-PBT.1: the 10x factor lives in ops/deep-pbt (never in the normal `npm test`)."""
    web = "\n".join(str(s.get("run", "")) for s in load(DEEP)["jobs"]["web"]["steps"])
    assert "--config ../ops/deep-pbt/vitest.deep.config.ts" in web
    setup = (REPO / "ops" / "deep-pbt" / "fast-check-deep.setup.ts").read_text()
    assert "FACTOR = 10" in setup and "configureGlobal" in setup
    assert "deep" not in (REPO / "web" / "package.json").read_text().split('"test"')[1].split(",")[0]


def test_a_deep_pbt_failure_opens_a_finding_and_a_needs_human_alert_but_still_ends_red():
    """REQ-OPS-PBT.2, REQ-OPS-ALERT.1: finding with the shrunk example, alert, and the job still fails."""
    for name, target in (("python", "engine"), ("web", "web")):
        steps = load(DEEP)["jobs"][name]["steps"]
        pbt = next(s for s in steps if s.get("id") == "pbt")
        assert pbt.get("continue-on-error") is True
        report = next(s for s in steps if "ci_channel.py" in str(s.get("run", "")))
        text = report["run"]
        assert f"finding --target {target}" in text and "--example-file" in text and "ci_channel.py alert" in text
        assert report.get("continue-on-error") is True and "failure" in report["if"]
        assert steps[-1]["run"].strip() == "exit 1" and "failure" in steps[-1]["if"]


def test_deep_pbt_passes_event_data_through_env_only():
    """REQ-OPS-PBT.2 (injection): no `${{` inside a run script."""
    for job in load(DEEP)["jobs"].values():
        for step in job["steps"]:
            assert "${{" not in str(step.get("run", ""))
