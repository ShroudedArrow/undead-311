"""Unit + property tests for pipeline/scripts/download.py (REQ-ING-1)."""

import importlib.util
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

SPEC = importlib.util.spec_from_file_location(
    "download", Path(__file__).parents[2] / "scripts" / "download.py"
)
download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download)


def test_data_dir_env_used_when_writable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    assert download.resolve_data_dir() == (tmp_path / "d").resolve()


def test_data_dir_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert download.resolve_data_dir() == download.repo_root() / ".local-data" / "data"


def test_data_dir_falls_back_when_not_writable(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("DATA_DIR", str(blocker / "sub"))  # parent is a file, so mkdir fails
    assert download.resolve_data_dir() == download.repo_root() / ".local-data" / "data"


@given(st.integers(min_value=2000, max_value=2040))
def test_wanted_resources_year_filter(year):
    pkg = {
        "resources": [
            {"name": f"311 Service Requests - {year}", "format": "CSV", "url": "u"},
            {"name": "dictionary", "format": "PDF", "url": "p"},
            {"name": "311 Service Requests - NEW SYSTEM", "format": "CSV", "url": "n"},
        ]
    }
    labels = [r["label"] for r in download.wanted_resources(pkg)]
    assert "new_system" in labels
    assert (str(year) in labels) == (year >= download.MIN_YEAR)
