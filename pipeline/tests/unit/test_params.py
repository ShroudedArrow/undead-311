"""REQ-DET-PARAM.1-3: parameters mirror .kiro/steering/zombie-definition.md exactly."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from undead311.detect.params import DEFAULT, DEFINITION_NAMES, Params
from undead311.ingest import closure_flags

DEFINITION = Path(__file__).resolve().parents[3] / ".kiro" / "steering" / "zombie-definition.md"


def _parameters_section() -> str:
    text = DEFINITION.read_text()
    start = text.index("## Parameters")
    end = text.index("## Algorithm")
    return text[start:end]


@pytest.mark.parametrize("name", DEFINITION_NAMES)
def test_req_det_param_3_default_matches_zombie_definition(name):
    """REQ-DET-PARAM.3: every default equals the number written in zombie-definition.md (fails on any mismatch)."""
    m = re.search(rf"\b{name}\s*=\s*(\d+(?:\.\d+)?)", _parameters_section())
    assert m, f"{name} not found in the Parameters section of zombie-definition.md"
    assert float(m.group(1)) == float(getattr(DEFAULT, name))


def test_req_det_param_1_all_nine_parameters_exist():
    """REQ-DET-PARAM.1: the nine parameters are defined in one module."""
    assert set(DEFINITION_NAMES) <= {f.name for f in dataclasses.fields(Params)}


def test_req_det_param_1_mirror_window_is_imported_from_closure_flags():
    """REQ-DET-PARAM.1: MIRROR_WINDOW_HOURS has one definition (closure_flags.py)."""
    assert DEFAULT.MIRROR_WINDOW_HOURS == closure_flags.MIRROR_WINDOW_HOURS


def test_req_det_param_2_params_are_frozen_and_overridden_only_by_argument(monkeypatch):
    """REQ-DET-PARAM.2: frozen dataclass; environment variables never change a default."""
    monkeypatch.setenv("RADIUS_M", "999")
    assert Params().RADIUS_M == 30
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.RADIUS_M = 5  # type: ignore[misc]
    assert dataclasses.replace(DEFAULT, RADIUS_M=50).RADIUS_M == 50


def test_req_det_match_4_grid_cell_covers_the_largest_rule_distance():
    """REQ-DET-MATCH.4: the largest of RADIUS_M, MAX_SEGMENT_DIST and 2 x INTERSECTION_M sizes the grid."""
    assert DEFAULT.max_match_dist_m == 75
    assert dataclasses.replace(DEFAULT, RADIUS_M=100).max_match_dist_m == 100
    assert dataclasses.replace(DEFAULT, matching="radius", RADIUS_M=15).max_match_dist_m == 15
