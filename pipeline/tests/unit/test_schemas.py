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
