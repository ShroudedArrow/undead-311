"""Checks on undead311/ingest/type_families.csv (REQ-DET-2 / REQ-ING-CATCH scope tiers)."""

import csv
from pathlib import Path

import pytest

CSV = Path(__file__).parents[2] / "undead311" / "ingest" / "type_families.csv"


@pytest.fixture(scope="module")
def rows():
    with CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def test_scope_tiers(rows):
    by_key = {(r["system"], r["type_raw"]): r for r in rows}
    assert by_key[("new", "Traffic Signal Request")]["scope_tier"] == "sensitivity"
    assert by_key[("new", "Traffic Signal Request")]["type_family"] == "traffic_signal"
    assert by_key[("new", "Street Light Other")]["scope_tier"] == "sensitivity"
    assert {r["scope_tier"] for r in rows} <= {"core", "sensitivity", "excluded"}


def test_no_duplicate_keys(rows):
    keys = [(r["system"], r["type_raw"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_crosswalk_exclusions(rows):
    by_key = {(r["system"], r["type_raw"]): r for r in rows}
    for t in ["Pruning Request", "Utility Contractor Complaints", "Unauthorized Signage", "Illegally Blocked Sidewalk"]:
        assert by_key[("new", t)]["scope_tier"] == "excluded"
        assert by_key[("new", t)]["city_originated_type"] == "false"


def test_catch_all_flag(rows):
    """REQ-DET-2 / REQ-ING-CATCH: only Street Light Other inherits its family via the link."""
    assert "catch_all" in rows[0]
    assert {r["catch_all"] for r in rows} <= {"true", "false"}
    assert [(r["system"], r["type_raw"]) for r in rows if r["catch_all"] == "true"] == [("new", "Street Light Other")]
