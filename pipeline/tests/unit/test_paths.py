"""REQ-ING-PATH.1-3: DATA_DIR fallback and worktree-safe repo root; REQ-ING-NIGHTLY.1-2 CLI shape."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from undead311 import paths
from undead311.cli import build_parser


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True
    )


@pytest.fixture
def main_repo(tmp_path):
    repo = tmp_path / "main"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_req_ing_path_1_unset_data_dir_uses_local_fallback(main_repo, monkeypatch):
    """REQ-ING-PATH.1: unset DATA_DIR -> <repo root>/.local-data/data, created."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    got = paths.data_dir(main_repo)
    assert got == (main_repo / ".local-data" / "data").resolve()
    assert got.is_dir()


def test_req_ing_path_1_missing_data_dir_uses_fallback(main_repo, monkeypatch, tmp_path):
    """REQ-ING-PATH.1: a DATA_DIR that does not exist is replaced by the fallback (and not created)."""
    missing = tmp_path / "nope"
    monkeypatch.setenv("DATA_DIR", str(missing))
    assert paths.data_dir(main_repo) == (main_repo / ".local-data" / "data").resolve()
    assert not missing.exists()


def test_req_ing_path_1_unwritable_data_dir_uses_fallback(main_repo, monkeypatch, tmp_path):
    """REQ-ING-PATH.1: a read-only DATA_DIR is replaced by the fallback (skipped when running as root)."""
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(ro, os.W_OK):
            pytest.skip("running as a user that can write to read-only folders")
        monkeypatch.setenv("DATA_DIR", str(ro))
        assert paths.data_dir(main_repo) == (main_repo / ".local-data" / "data").resolve()
    finally:
        ro.chmod(0o700)


def test_req_ing_path_1_valid_data_dir_is_kept(main_repo, monkeypatch, tmp_path):
    """REQ-ING-PATH.1: an existing writable DATA_DIR is used as given."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert paths.data_dir(main_repo) == tmp_path.resolve()


def test_req_ing_path_2_worktree_resolves_to_main_checkout(main_repo, tmp_path, monkeypatch):
    """REQ-ING-PATH.2: from inside a git worktree the repo root is the MAIN checkout, so data is shared."""
    wt = tmp_path / "wt"
    _git(main_repo, "worktree", "add", "-q", str(wt), "-b", "side")
    assert paths.repo_root(wt) == main_repo.resolve()
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert paths.data_dir(wt) == (main_repo / ".local-data" / "data").resolve()


def test_req_ing_path_2_not_a_git_repo_falls_back_to_package_location(tmp_path):
    """REQ-ING-PATH.2: outside any repo the root is derived from the package location, never a fixed path."""
    assert paths.repo_root(tmp_path) == Path(paths.__file__).resolve().parents[2]


def test_req_ing_nightly_cli_accepts_pipeline_and_sample_flag():
    """REQ-ING-NIGHTLY.1-2: `python -m undead311 pipeline [--sample]`."""
    p = build_parser()
    assert p.parse_args(["pipeline"]).sample is False
    assert p.parse_args(["pipeline", "--sample"]).sample is True
    with pytest.raises(SystemExit):
        p.parse_args([])


def test_req_ing_path_3_makefile_pipeline_targets_run_the_cli():
    """REQ-ING-NIGHTLY.1-2, REQ-ING-PATH.3: make targets call the CLI under the Makefile's DATA_DIR rule."""
    text = (Path(__file__).resolve().parents[3] / "Makefile").read_text()
    assert "python -m undead311 pipeline --sample" in text
    assert "python -m undead311 pipeline\n" in text
    assert "export DATA_DIR" in text
