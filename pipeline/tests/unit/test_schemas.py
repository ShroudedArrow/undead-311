"""Schema scaffold checks (REQ-EXP-1.1, testing.md #16): every schema is valid and the owner's answer key fits its schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[3]
SCHEMAS = sorted((REPO / "schemas").glob("*.schema.json"))
ENGINE = {"zombies", "incidents", "points", "card", "exclusions", "separate_deaths", "repeat_offenders", "bulk_closures",
          "status", "test_town_expected"}
STATS = {"scorecard", "excess", "survival", "funnel", "groups", "sensitivity_grid", "temporary_fixes", "validation", "judge_tour"}
ANSWER_KEY = REPO / "pipeline" / "tests" / "fixtures" / "expected_zombies.json"


def test_every_schema_named_by_the_designs_exists():
    """REQ-EXP-1.1, REQ-STAT-EXP.1: all engine and stats schemas are present."""
    names = {p.name.removesuffix(".schema.json") for p in SCHEMAS}
    assert (ENGINE | STATS) <= names


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.stem)
def test_schema_is_valid_draft_2020_12(path):
    """REQ-EXP-1.1: each schema passes the meta-schema; data files carry data_version (REQ-EXP-1.2)."""
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    if path.name != "test_town_expected.schema.json":
        assert "data_version" in schema["required"]


def test_answer_key_validates_against_its_schema():
    """REQ-DET-GOLD: the owner's answer key fits test_town_expected.schema.json (read only, never edited)."""
    schema = json.loads((REPO / "schemas" / "test_town_expected.schema.json").read_text())
    Draft202012Validator(schema).validate(json.loads(ANSWER_KEY.read_text()))


def test_excess_schema_accepts_the_shift_and_placebo_results_and_rejects_a_malformed_one():
    """REQ-STAT-SHIFT, REQ-STAT-PLACEBO, REQ-EXP-1.1, testing.md #7 and #16 (ops#64, ops#92): both results are optional
    objects, but a present one has typed fields, and a shift result with no seed is rejected (a fixed seed is the contract)."""
    validator = Draft202012Validator(json.loads((REPO / "schemas" / "excess.schema.json").read_text()))
    ok = {"data_version": "v", "rows": [],
          "shift": {"runs": 1000, "seed": 311, "observed": 10, "mean": 1.5, "q025": 0.0, "q975": 4.0},
          "placebo": {"excess": 0.1, "lo": -1.0, "hi": 1.2}}  # fmt: skip
    assert not list(validator.iter_errors(ok)) and not list(validator.iter_errors({"data_version": "v", "rows": []}))
    assert list(validator.iter_errors({**ok, "shift": {"runs": 1000}}))
    assert list(validator.iter_errors({**ok, "shift": {k: v for k, v in ok["shift"].items() if k != "seed"}}))
    assert list(validator.iter_errors({**ok, "placebo": {"excess": "x", "lo": 0, "hi": 0}}))
    assert list(validator.iter_errors({**ok, "shift": 5})) and list(validator.iter_errors({**ok, "placebo": "none"}))



def _schema(name: str) -> dict:
    return json.loads((REPO / "schemas" / f"{name}.schema.json").read_text())


def test_city_rereport_is_promised_by_every_file_that_carries_a_tier_count():
    """REQ-EXP-1.1, REQ-DET-TIER.3, ZD step 6 (ops#126): the fourth tier is required wherever source_unknown is, so the
    web app's tier toggle can rely on it."""
    zombie = _schema("zombies")["properties"]["zombies"]["items"]
    assert "city_rereport" in zombie["required"] and zombie["properties"]["city_rereport"]["type"] == "boolean"
    counts = _schema("scorecard")["properties"]["counts"]
    assert "city_rereport" in counts["required"] and "city_rereport" in counts["properties"]
    assert "city_rereport" in _schema("sensitivity_grid")["properties"]["points"]["items"]["required"]
    for name in ("funnel", "groups"):
        assert "city_rereport" in _schema(name)["properties"]["all_tiers"]["description"]
