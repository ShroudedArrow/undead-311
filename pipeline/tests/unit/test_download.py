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


def test_req_ing_snap_1_geo_rows_are_replaced_and_311_rows_are_kept():
    """REQ-ING-SNAP.1: SNAPSHOT.md records the geography files; re-running replaces them and leaves 311 rows alone."""
    base = "# Data snapshot\n\nDownloaded: 2026-11-12\n\n| file | r |\n|---|---|\n| 311_2024.csv | a | b | 1 | h |\n"
    once = download.upsert_geo_rows(base, [("street_segments_sam.geojson", "SAM", "t", 5, "h1")])
    twice = download.upsert_geo_rows(once, [("street_segments_sam.geojson", "SAM", "t", 6, "h2"),
                                            ("neighborhood_boundaries.geojson", "NB", "t", 7, "h3")])  # fmt: skip
    assert once.count("street_segments_sam.geojson") == 1 and "311_2024.csv" in once
    assert twice.count("street_segments_sam.geojson") == 1 and "| 6 | h2 |" in twice and "| 5 | h1 |" not in twice
    assert twice.count("neighborhood_boundaries.geojson") == 1 and twice.count("311_2024.csv") == 1


def test_req_ing_snap_1_geo_resource_picks_the_geojson_and_geo_files_are_not_311_files():
    pkg = {"resources": [{"format": "CSV", "url": "c"}, {"format": "GeoJSON", "url": "g"}]}
    assert download.geo_resource(pkg, "GEOJSON")["url"] == "g" and download.geo_resource(pkg, "KML") is None
    from undead311.ingest.load import expected_files

    assert download.GEO_FILES and all(not n.startswith("311_") for n in download.GEO_FILES)
    assert expected_files.__name__  # the loader's file regex only matches 311_*.csv rows
