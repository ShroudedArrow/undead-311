"""REQ-DET-PF (ops#29): the share of headline resurrections that are legacy city-originated is reported, never filtered."""

from __future__ import annotations

from helpers import mk

from undead311.detect.core import city_origin_summary, detect, is_city_originated


def summary(cases):
    return city_origin_summary(detect(cases), {c.id: c for c in cases})


def test_req_det_pf_2_only_legacy_cases_can_be_known_city_originated():
    """REQ-DET-PF.2: legacy city source or internal type is city-originated; a new-system case never is."""
    assert is_city_originated(mk("a", 0, source="Employee Generated"))
    assert is_city_originated(mk("b", 0, city_type=True))
    assert not is_city_originated(mk("c", 0, source="Constituent Call"))
    assert not is_city_originated(mk("d", 0, system="new", source="Employee Generated"))


def test_req_det_tier_3_city_re_reports_form_their_own_tier_outside_the_headline():
    """REQ-DET-TIER.3 (ZD step 6, ops#29): of three re-reports, the two city-originated ones are tier city_rereport; one
    of them opened under 1 h after the closure. The resident's is the whole headline."""
    cs = [
        mk("A1", 0, 1, x=0), mk("R1", 1, source="Employee Generated", close_hours=0, open_hours=0.5),
        mk("A2", 0, 1, x=300), mk("R2", 5, x=300, city_type=True),
        mk("A3", 0, 1, x=600), mk("R3", 5, x=600),
    ]
    r = detect(cs)
    assert {z.incident_id: (z.tier, z.city_rereport) for z in r.zombies} == {
        "A1": ("city_rereport", True), "A2": ("city_rereport", True), "A3": ("headline", False),
    }  # fmt: skip
    s = city_origin_summary(r, {c.id: c for c in cs})
    assert s["headline"] == 1 and s["city_rereport"] == 2 and s["city_rereport_under_1h"] == 1
    assert abs(s["city_rereport_share"] - 2 / 3) < 1e-9


def test_req_det_tier_3_a_city_re_report_still_counts_in_the_chain_total_but_not_the_headline_count():
    """REQ-DET-TIER.3, ZD step 7: `times_risen` counts every tier; the repeat-offender test counts headline zombies."""
    cs = [mk("A", 0, 1), mk("B", 5, 6, source="Employee Generated"), mk("C", 10, 11), mk("D", 15, 16), mk("E", 20)]
    r = detect(cs)
    tiers = {z.incident_id: z.tier for z in r.zombies}
    assert tiers == {"A": "city_rereport", "B": "headline", "C": "headline", "D": "headline"}  # keyed by the original
    (chain,) = r.chains
    assert chain.times_risen == 4 and chain.headline_count == 3 and chain.repeat_offender


def test_req_det_tier_3_a_planned_follow_up_is_not_a_city_re_report():
    """ZD step 6: a city re-report after a planned-follow-up closure is a planned follow-up, not a zombie in any tier."""
    r = detect([mk("A", 0, 1, label="made_safe_temporary"), mk("R", 5, source="Employee Generated")])
    assert r.zombies == [] and len(r.planned_followups) == 1


def test_req_det_tier_3_a_resident_re_report_after_made_safe_stays_headline():
    """ZD step 6: only a city-originated re-report moves out; a resident's stays headline, tagged after_temporary_fix."""
    r = detect([mk("A", 0, 1, label="made_safe_temporary"), mk("R", 5)])
    (z,) = r.zombies
    assert z.tier == "headline" and z.after_temporary_fix and not z.city_rereport


def test_req_det_tier_3_empty_town_has_zero_share():
    """REQ-DET-TIER.3: no headline or city zombies gives a share of 0, not a division error."""
    assert summary([mk("A", 0, 1)]) == {"headline": 0, "city_rereport": 0, "city_rereport_under_1h": 0,
                                         "city_rereport_share": 0.0}  # fmt: skip
