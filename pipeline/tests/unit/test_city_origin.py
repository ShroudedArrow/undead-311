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


def test_req_det_pf_counts_city_originated_headline_resurrections_and_those_under_one_hour():
    """REQ-DET-PF: three headline zombies, two with city-originated re-reports, one of them within 1 h of the closure."""
    cs = [
        mk("A1", 0, 1, x=0), mk("R1", 1, source="Employee Generated", close_hours=0, open_hours=0.5),
        mk("A2", 0, 1, x=300), mk("R2", 5, x=300, city_type=True),
        mk("A3", 0, 1, x=600), mk("R3", 5, x=600),
    ]
    s = summary(cs)
    assert s["headline"] == 3 and s["city_originated"] == 2 and s["city_originated_under_1h"] == 1
    assert abs(s["city_originated_share"] - 2 / 3) < 1e-9


def test_req_det_pf_empty_town_has_zero_share():
    """REQ-DET-PF: no headline zombies gives a share of 0, not a division error."""
    assert summary([mk("A", 0, 1)]) == {"headline": 0, "city_originated": 0, "city_originated_under_1h": 0,
                                         "city_originated_share": 0.0}  # fmt: skip
