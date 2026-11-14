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
