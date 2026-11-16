"""Property P19: confidence is in [0, 1]; confidence_partial is true exactly when a term is neutral (REQ-CONF.1-2)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from strategies import town

from undead311.detect.confidence import LABEL_TERM, NEUTRAL, ConfidenceInputs, confidence, terms
from undead311.detect.core import detect

inputs = st.builds(
    ConfidenceInputs,
    match_mode=st.sampled_from(["segment", "intersection", "radius"]),
    distance_m=st.floats(0, 500),
    gap_days=st.floats(0, 200),
    label=st.sampled_from(sorted(LABEL_TERM)),
    bulk_closure=st.booleans(),
    catch_all=st.booleans(),
    baseline_p=st.one_of(st.none(), st.floats(0, 1)),
    skeptic_verdict=st.sampled_from(["survives", "weakened", "explained_away", "not_reviewed"]),
)


@given(inputs)
def test_prop_p19_confidence_in_unit_interval_and_partial_iff_a_term_is_neutral(i):
    """REQ-CONF.1-2: score within [0, 1]; partial exactly when baseline is missing or the verdict is not_reviewed."""
    score, partial = confidence(i)
    assert 0.0 <= score <= 1.0
    assert partial == (i.baseline_p is None or i.skeptic_verdict == "not_reviewed")
    t = terms(i)
    assert all(0.0 <= v <= 1.0 for v in t.values())
    assert (t["baseline"] == NEUTRAL and i.baseline_p is None) or i.baseline_p is not None


@given(town())
def test_prop_p19_every_detected_zombie_has_a_valid_score(cases):
    """REQ-CONF.1-2: detector output carries in-range scores, partial because no baseline or Skeptic yet."""
    for z in detect(cases).zombies:
        assert 0.0 <= z.confidence <= 1.0 and z.confidence_partial
