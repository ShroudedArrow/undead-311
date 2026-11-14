"""Makefile DATA_DIR / UV_CACHE_DIR fallback (tech.md self-correcting fallback; channel finding ops#9)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def make_value(var: str, env: dict[str, str]) -> str:
    base = {k: v for k, v in os.environ.items() if k not in ("DATA_DIR", "UV_CACHE_DIR")}
    out = subprocess.run(["make", "-s", "-f", "-", "show"], cwd=REPO, env={**base, **env}, capture_output=True, text=True,
                         check=True, input=f"include Makefile\nshow:\n\t@echo $({var})\n")
    return out.stdout.strip()


def test_unset_data_dir_falls_back_to_repo_local_folder():
    """tech.md: unset DATA_DIR resolves to <repo root>/.local-data/data."""
    assert make_value("DATA_DIR", {}).endswith("/.local-data/data")


def test_missing_data_dir_falls_back(tmp_path):
    """ops#9: a DATA_DIR that does not exist is replaced by the fallback."""
    assert make_value("DATA_DIR", {"DATA_DIR": str(tmp_path / "nope")}).endswith("/.local-data/data")


def test_unwritable_data_dir_falls_back(tmp_path):
    """ops#9: a DATA_DIR that is not writable is replaced by the fallback (skipped when running as root)."""
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(ro, os.W_OK):
            return
        assert make_value("DATA_DIR", {"DATA_DIR": str(ro)}).endswith("/.local-data/data")
    finally:
        ro.chmod(0o700)


def test_valid_data_dir_is_kept(tmp_path):
    """ops#9: an existing writable DATA_DIR is used as given; same for UV_CACHE_DIR."""
    assert make_value("DATA_DIR", {"DATA_DIR": str(tmp_path)}) == str(tmp_path)
    assert make_value("UV_CACHE_DIR", {"UV_CACHE_DIR": str(tmp_path)}) == str(tmp_path)


def test_test_and_lint_install_web_deps_first():
    """testing.md definition of done 1-2 (ops#121): `make test` and `make lint` depend on web-deps, so a fresh worktree
    installs web/node_modules instead of failing on `vitest: command not found`."""
    out = subprocess.run(["make", "-n", "-s", "test", "lint"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert out.count("npm ci") >= 1 or (REPO / "web/node_modules/vitest").is_dir()
    mk = (REPO / "Makefile").read_text()
    assert "\ntest: web-deps" in mk and "\nlint: web-deps" in mk
