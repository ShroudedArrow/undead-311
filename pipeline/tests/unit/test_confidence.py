"""REQ-CONF.1-3: confidence formula, neutral terms, partial flag; docs/METHODS.md documents it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from helpers import mk

from undead311.detect.confidence import WEIGHTS, ConfidenceInputs, confidence, match_term, rescore, terms
from undead311.detect.core import detect

METHODS = Path(__file__).resolve().parents[3] / "docs" / "METHODS.md"


def inp(**kw):
    base = {"match_mode": "segment", "distance_m": 0.0, "gap_days": 0.0, "label": "resolved"}
    return ConfidenceInputs(**{**base, **kw})


def test_req_conf_1_weights_sum_to_one_and_best_case_with_evidence_is_one():
    """REQ-CONF.1: weights add to 1; a perfect match with all evidence scores 1.0."""
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    score, partial = confidence(inp(baseline_p=0.0, skeptic_verdict="survives"))
    assert score == pytest.approx(1.0) and partial is False


def test_req_conf_1_match_term_orders_segment_over_intersection_over_radius():
    """REQ-CONF.1: at the same small distance segment > intersection > radius; closer is higher."""
    assert match_term("segment", 10) > match_term("intersection", 10) > match_term("radius", 10)
    assert match_term("segment", 10) > match_term("segment", 60)
    assert match_term("radius", 30) == 0 and match_term("segment", 150) == 0


def test_req_conf_1_shorter_gap_and_better_label_score_higher():
    """REQ-CONF.1: gap and label terms move the score the right way."""
    assert confidence(inp(gap_days=1))[0] > confidence(inp(gap_days=50))[0]
    assert confidence(inp(label="resolved"))[0] > confidence(inp(label="referred"))[0]


def test_req_conf_1_bulk_closure_lowers_the_label_term_without_changing_the_label():
    """REQ-CONF.1: bulk closure caps the label term at 0.5."""
    assert terms(inp(bulk_closure=True))["label"] == 0.5 and terms(inp(label="bulk_backlog"))["label"] == 0.5
    assert confidence(inp(bulk_closure=True))[0] < confidence(inp())[0]


def test_req_conf_1_catch_all_specificity_is_lower():
    """REQ-CONF.1: an inherited catch-all type scores 0.7 on specificity."""
    assert terms(inp(catch_all=True))["specificity"] == 0.7 and terms(inp())["specificity"] == 1.0


def test_req_conf_2_neutral_terms_and_partial_flag():
    """REQ-CONF.2: missing baseline_p or a not_reviewed verdict uses 0.5 and sets confidence_partial."""
    t = terms(inp())
    assert t["baseline"] == 0.5 and t["skeptic"] == 0.5
    assert confidence(inp())[1] is True
    assert confidence(inp(baseline_p=0.1))[1] is True  # skeptic still neutral
    assert confidence(inp(skeptic_verdict="survives"))[1] is True  # baseline still neutral
    assert confidence(inp(baseline_p=0.1, skeptic_verdict="weakened"))[1] is False


def test_req_conf_detect_attaches_a_partial_confidence_to_every_zombie():
    """REQ-CONF.2: the detector scores zombies with neutral terms; rescore fills in evidence later."""
    (z,) = detect([mk("A", 0, 1), mk("R", 5)]).zombies
    assert z.confidence_partial and 0 < z.confidence < 1 and z.baseline_p is None
    better = rescore(z, baseline_p=0.01, skeptic_verdict="survives", skeptic_notes="held up")
    assert not better.confidence_partial and better.confidence > z.confidence and better.skeptic_notes == "held up"


def test_req_conf_1_methods_md_documents_the_formula_and_marks_it_pending():
    """REQ-CONF.1: docs/METHODS.md has the section "Confidence score", the weights, and "pending owner approval"."""
    text = METHODS.read_text()
    assert "## Confidence score" in text and "pending owner approval" in text
    for name, w in WEIGHTS.items():
        assert re.search(rf"{w:.2f}\*{name}", text), name
