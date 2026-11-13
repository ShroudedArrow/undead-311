"""REQ-DET-1.1-1.4: incidents (true duplicates only)."""

from __future__ import annotations

from helpers import mk, params

from undead311.detect.core import detect


def incidents(cases, p=None):
    r = detect(cases, p) if p else detect(cases)
    return {i.incident_id: i for i in r.incidents}


def test_req_det_1_2_duplicates_reported_while_open_form_one_incident():
    """REQ-DET-1.2: three reports of one problem, all opened before the first closure, are one incident."""
    cs = [mk("A", 0, 2, x=0), mk("B", 0.5, 2.1, x=5), mk("C", 1, 2.2, x=9)]
    inc = incidents(cs)
    assert list(inc) == ["A"] and inc["A"].member_ids == ("A", "B", "C")


def test_req_det_1_3_close_time_and_label_come_from_the_latest_closing_member():
    """REQ-DET-1.3: close = latest member close; label = that member's label."""
    cs = [mk("A", 0, 2, label="resolved"), mk("B", 0.5, 2.5, label="duplicate"), mk("C", 1, 2.2, label="noted")]
    inc = incidents(cs)["A"]
    assert inc.coroner_label == "duplicate" and inc.close_utc == cs[1].close_utc


def test_req_det_1_3_equal_close_times_break_the_label_tie_by_member_id():
    """REQ-DET-1.3: same latest close -> the smallest member ID's label."""
    cs = [mk("B", 0, 2, label="noted"), mk("A", 1, 2, label="resolved")]
    inc = incidents(cs)["A"]
    assert inc.member_ids == ("A", "B") and inc.coroner_label == "resolved"


def test_req_det_1_4_a_fast_resurrection_is_not_swallowed_by_its_original():
    """REQ-DET-1.4: R opens after the closure (even 1 day later and closed within 3 days): its own incident."""
    cs = [mk("A", 0, 1), mk("B", 2, 3)]
    assert sorted(incidents(cs)) == ["A", "B"]


def test_req_det_1_4_a_case_opened_at_the_closing_instant_is_not_a_member():
    """REQ-DET-1.4: opening exactly at the incident's earliest close is not 'before' it."""
    cs = [mk("A", 0, 1), mk("B", 1, 2)]
    assert sorted(incidents(cs)) == ["A", "B"]


def test_req_det_1_2_span_over_seven_days_starts_a_new_incident():
    """REQ-DET-1.2 + clarification S12/S17: would join but breaks INCIDENT_MAX_SPAN_DAYS -> its own incident."""
    cs = [mk("A", 0, 3), mk("B", 2, 8.5)]  # first open to last close = 8.5 days
    assert sorted(incidents(cs)) == ["A", "B"]
    assert sorted(incidents([mk("A", 0, 3), mk("B", 2, 7)])) == ["A"]  # exactly 7 days is allowed


def test_req_det_1_2_family_and_location_must_match():
    """REQ-DET-1.2: another family or a far-away case never joins."""
    cs = [mk("A", 0, 2), mk("B", 0.5, 2, family="sign"), mk("C", 0.5, 2, x=140)]
    assert sorted(incidents(cs)) == ["A", "B", "C"]


def test_req_det_1_2_the_smallest_incident_id_wins_when_several_qualify():
    """REQ-DET-1.2: c matches two incidents -> joins the one with the smaller ID."""
    cs = [mk("B", 0, 2, x=-20), mk("A", 0.1, 2, x=20), mk("C", 0.2, 2, x=0)]
    # B and A are 40 m apart (no match, radius 30) so separate; C is 20 m from both
    inc = incidents(cs)
    assert inc["A"].member_ids == ("A", "C") and inc["B"].member_ids == ("B",)


def test_req_det_1_1_open_cases_are_never_members_and_out_of_scope_tiers_are_ignored():
    """REQ-DET-1.1: only closed in-scope cases are in incidents."""
    cs = [mk("A", 0, 2), mk("B", 0.5), mk("C", 0.5, 2)]
    assert incidents(cs)["A"].member_ids == ("A", "C")
    assert incidents(cs, params(INCIDENT_MAX_SPAN_DAYS=1)).keys() == {"A", "C"}
