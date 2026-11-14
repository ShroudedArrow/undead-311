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

TAG_REF = re.compile(r"^v?\d+(\.\d+){0,2}([-+.][0-9A-Za-z.-]+)?$")   # v4, v4.2.1, 1.2.3
SHA_REF = re.compile(r"^[0-9a-f]{40}$")


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


@pytest.mark.parametrize(
    "uses",
    ["actions/checkout", "actions/checkout@main", "actions/checkout@master", "owner/repo@feature-x",
     "owner/repo@abc123", "docker://node:22"],
)
def test_the_pin_check_rejects_moving_refs(uses):
    """REQ-OPS-CI.4: the O1 checker bites. Branches, short SHAs, bare names and untagged images fail."""
    assert unpinned(uses)


@pytest.mark.parametrize(
    "uses",
    ["actions/checkout@v4", "actions/setup-node@v4.1.0", "astral-sh/setup-uv@v5", "./local-action",
     "actions/checkout@" + "a" * 40, "docker://node@sha256:" + "b" * 64],
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
