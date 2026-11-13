"""Properties P16, P17, P18: catch-all headline rule, one tier per zombie, step 6 outcomes. REQ-DET-TIER, REQ-DET-PF."""

from __future__ import annotations

from helpers import mk
from hypothesis import given
from hypothesis import strategies as st
from strategies import LABELS, SOURCES, town

from undead311.detect.core import CITY_SOURCES, PF_LABELS, detect


@given(town())
def test_prop_p16_sensitivity_cases_never_enter_the_headline(cases):
    """REQ-DET-TIER.4, REQ-ING-CATCH.3: an unlinked or ambiguous catch-all (tier sensitivity) is never headline."""
    by_id = {c.id: c for c in cases}
    for z in detect(cases).zombies:
        touched = [by_id[m] for m in z.member_ids] + [by_id[z.resurrection_id]]
        if any(c.scope_tier == "sensitivity" for c in touched):
            assert z.tier == "sensitivity"
        if z.tier == "headline":
            assert all(c.scope_tier == "core" for c in touched)


@given(town())
def test_prop_p17_exactly_one_tier_and_headline_count_equals_headline_zombies(cases):
    """REQ-DET-TIER.1-2: every zombie has one valid tier; the counts add up; flags agree with tiers."""
    r = detect(cases)
    assert all(z.tier in ("headline", "source_unknown", "sensitivity") for z in r.zombies)
    assert r.headline_count == sum(1 for z in r.zombies if z.tier == "headline")
    assert r.count("headline") + r.count("source_unknown") + r.count("sensitivity") == len(r.zombies)
    assert len({z.zombie_id for z in r.zombies}) == len(r.zombies)
    assert all(z.source_unknown for z in r.zombies if z.tier == "source_unknown")


@given(
    st.sampled_from(LABELS),
    st.sampled_from(["legacy", "new"]),
    st.sampled_from(SOURCES),
    st.booleans(),
)
def test_prop_p18_step_6_outcomes_for_every_label_system_and_source(label, system, source, city_type):
    """REQ-DET-PF.1-4: the outcome for each (original label, re-report system, source, type) combination."""
    r = detect([mk("A", 0, 1, label=label), mk("R", 10, system=system, source=source, city_type=city_type)])
    city = system == "legacy" and (source in CITY_SOURCES or city_type)
    if label in ("invalid", "duplicate"):
        assert not r.zombies and not r.planned_followups and len(r.separate_deaths) == 1
    elif label in PF_LABELS and city:
        assert not r.zombies and len(r.planned_followups) == 1
    else:
        (z,) = r.zombies
        assert z.after_temporary_fix == (system == "legacy" and label == "made_safe_temporary")
        assert z.source_unknown == (system == "new" and label in PF_LABELS)
        assert z.tier == ("source_unknown" if z.source_unknown else "headline")
