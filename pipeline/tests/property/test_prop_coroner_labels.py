"""Property P5: every joined Coroner label is in the allowed set; an unknown label raises (REQ-COR-1.4, testing.md #9)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from undead311.coroner.join import ALLOWED_LABELS, UnknownLabel, assign_label, check_label

systems = st.sampled_from(["legacy", "new"])
codes = st.sampled_from([None, "Resolved", "Resolved successfully", "Noted", "Transitioned", "Other code"])
templates = st.text(max_size=12)
good_maps = st.dictionaries(templates, st.sampled_from(ALLOWED_LABELS), max_size=5)


@given(systems, codes, templates, good_maps)
def test_prop_p5_every_assigned_label_is_in_the_allowed_set(system, code, template, labels):
    """REQ-COR-1.4: assign_label only ever returns an allowed label."""
    label, unlabeled = assign_label(system, code, template, labels)
    assert label in ALLOWED_LABELS
    assert unlabeled == (label == "other" and template not in labels)


@given(systems, templates, st.text(min_size=1, max_size=10).filter(lambda s: s not in ALLOWED_LABELS))
def test_prop_p5_an_unknown_label_raises(system, template, bad):
    """REQ-COR-1.4: a label outside the set raises instead of passing through."""
    with pytest.raises(UnknownLabel):
        check_label(bad)
    if system == "legacy":
        with pytest.raises(UnknownLabel):
            assign_label(system, None, template, {template: bad})
