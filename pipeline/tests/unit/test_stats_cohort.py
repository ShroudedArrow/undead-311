"""REQ-STAT-SF.1 (denominator), glossary: eligible originals, spot keys, seasons."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from helpers import day, mk

from undead311.detect.core import detect
from undead311.stats.cohort import eligible_originals, season, spot_key

END = day(200)


def first_members(incidents) -> set[str]:
    return {i.member_ids[0] for i in incidents}


def test_req_stat_sf_1_only_fully_observed_incidents_are_eligible():
    """close + WINDOW_DAYS <= data end. A closes on day 1 (eligible); B closes 59 days before END (not yet)."""
    incidents = detect([mk("A", 0, 1), mk("B", 100, 141, x=500.0)]).incidents
    by_first = {i.member_ids[0]: i for i in incidents}
    assert first_members(eligible_originals(incidents, END)) == {"A"}
    assert by_first["B"].close_utc + timedelta(days=60) > END
    # the boundary itself is eligible
    edge = by_first["B"].close_utc + timedelta(days=60)
    assert first_members(eligible_originals(incidents, edge)) == {"A", "B"}


def test_req_stat_sf_1_a_mirror_pair_is_one_original_in_the_denominator():
    """REQ-STAT-SF.1, ZD step 9 (ops#46): the same report filed in both systems within 6 h counts once; the later copy
    forms no incident."""
    r = detect([mk("L", 0, 0, close_hours=1), mk("N", 0, 1, system="new", open_hours=3), mk("B", 0, 1, x=500.0)])
    assert first_members(eligible_originals(r.incidents, END)) == {"L", "B"}
    assert r.mirror_ids == {"N"}


def test_req_stat_sf_1_a_transferred_incident_is_never_eligible():
    incidents = detect([mk("A", 0, 1, text="Resubmitted as BCS-123"), mk("B", 0, 1, x=500.0)]).incidents
    assert first_members(eligible_originals(incidents, END)) == {"B"}


def test_req_stat_sf_1_sensitivity_scope_incidents_only_join_the_all_tier_cohort():
    incidents = detect([mk("A", 0, 1), mk("S", 0, 1, x=500.0, tier="sensitivity")]).incidents
    assert first_members(eligible_originals(incidents, END)) == {"A"}
    assert first_members(eligible_originals(incidents, END, all_tiers=True)) == {"A", "S"}


def test_glossary_seasons_are_meteorological():
    expected = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 5: "spring"}
    expected |= {6: "summer", 8: "summer", 9: "autumn", 11: "autumn"}
    for month, name in expected.items():
        assert season(datetime(2024, month, 15, tzinfo=UTC)) == name


def test_glossary_spot_is_the_segment_when_snapped_else_a_60_m_cell():
    assert spot_key("SEG-1", 42.3, -71.1) == "seg:SEG-1"
    a = spot_key(None, 42.3000, -71.1000)
    assert a.startswith("cell:") and a == spot_key(None, 42.30001, -71.10001)  # about 1 m away: same cell
    assert a != spot_key(None, 42.3010, -71.1000)  # about 111 m north: another cell
