"""REQ-DET-2.1-2.5 and REQ-DET-3.1-3.3: candidate pairs, mirrors, transfers, attribution."""

from __future__ import annotations

import pytest
from helpers import mk

from undead311.detect.core import candidate_pairs, detect


def zs(cases, **kw):
    return {z.incident_id: z for z in detect(cases, **kw).zombies}


def test_req_det_2_1_a_reopen_after_the_close_within_the_window_is_a_possible_zombie():
    """REQ-DET-2.1, REQ-DET-3.3: resurrection, reports_after and gap_days."""
    z = zs([mk("A", 0, 2), mk("B", 12, 13), mk("C", 12.5)])["A"]
    assert (z.resurrection_id, z.reports_after) == ("B", 2)
    assert z.gap_days == pytest.approx(10.0)
    assert z.match_mode == "radius"


def test_req_det_2_1_re_report_must_open_strictly_after_the_close():
    """REQ-DET-2.1: opening at the close instant or earlier is not a re-report."""
    assert zs([mk("A", 0, 2), mk("B", 2)]) == {}
    assert "A" in zs([mk("A", 0, 2), mk("B", 2, open_hours=0.5)])


def test_req_det_2_1_window_is_measured_from_the_incident_close():
    """REQ-DET-2.1: 60 days after the incident's (latest) close is inside, one hour later is outside."""
    inside = [mk("A", 0, 2), mk("B", 0.5, 4), mk("R", 64)]  # incident closes day 4; R at day 64 = close + 60
    assert "A" in zs(inside)
    outside = [mk("A", 0, 2), mk("B", 0.5, 4), mk("R", 64, open_hours=1)]
    assert zs(outside) == {}


def test_req_det_2_1_a_member_is_never_its_own_zombie():
    """REQ-DET-2.1: duplicates inside one incident are not re-reports of it."""
    assert zs([mk("A", 0, 2), mk("B", 0.5, 2.5)]) == {}


def test_req_det_3_1_each_re_report_attaches_to_the_most_recent_incident():
    """REQ-DET-3.1: with two eligible incidents the one that closed later gets R."""
    cs = [mk("A", 0, 1), mk("B", 10, 11), mk("R", 20)]
    r = detect(cs)
    assert r.attribution["R"] == "B"
    assert {z.incident_id: z.resurrection_id for z in r.zombies} == {"A": "B", "B": "R"}


def test_req_det_3_1_attribution_ties_break_by_incident_id():
    """REQ-DET-3.1: two incidents closing at the same instant -> the smaller incident ID."""
    cs = [mk("B", 0, 1, x=-20), mk("A", 0, 1, x=20), mk("R", 5, x=0)]
    assert detect(cs).attribution["R"] == "A"


def test_req_det_3_2_a_re_report_that_closes_starts_its_own_incident_and_chains():
    """REQ-DET-3.2/3.3: R counted once; being closed it is also an incident of its own."""
    r = detect([mk("A", 0, 1), mk("B", 5, 6)])
    assert [z.incident_id for z in r.zombies] == ["A"] and {i.incident_id for i in r.incidents} == {"A", "B"}


def test_req_det_2_4_cross_system_copy_within_six_hours_is_a_mirror_not_a_zombie():
    """REQ-DET-2.4: legacy original and a new-system copy opened 3 h later attach to nothing; only the later copy is the
    mirror (ZD step 9, ops#30)."""
    r = detect([mk("A", 0, 0, close_hours=1), mk("N", 0, system="new", open_hours=3)])
    assert r.zombies == [] and r.attribution == {} and r.excluded_pairs["mirror"] == 1
    assert r.mirror_ids == {"N"}


def test_req_det_2_4_the_earlier_copy_can_resurrect_another_incident_and_the_later_copy_is_dropped():
    """REQ-DET-2.4, ops#30: one report filed in both systems resurrects an older closure once, through its earlier copy."""
    r = detect([mk("P", 0, 1), mk("O", 40, 41), mk("N", 40, 42, system="new", open_hours=1)])
    assert [(z.incident_id, z.resurrection_id, z.reports_after) for z in r.zombies] == [("P", "O", 1)]
    assert r.mirror_ids == {"N"} and r.attribution == {"O": "P"}


def test_req_det_2_4_a_mirror_copy_is_in_no_incident_and_so_counts_once():
    """REQ-DET-1.1, REQ-DET-2.4, ops#30/#46: a closed later copy forms no incident of its own, so the pair is one original."""
    r = detect([mk("O", 0, 1), mk("N", 0, 2, system="new", open_hours=1)])
    assert [i.member_ids for i in r.incidents] == [("O",)] and r.mirror_ids == {"N"}


def test_req_det_2_4_a_copy_of_a_mirror_is_not_a_mirror_itself():
    """REQ-DET-2.4: A (legacy), B (new, +1 h), C (legacy, +2 h): B mirrors A; C is the same system as A, so it is a normal
    case that can resurrect A's incident."""
    r = detect([mk("A", 0, 0, close_hours=0.5), mk("B", 0, system="new", open_hours=1), mk("C", 0, open_hours=2)])
    assert r.mirror_ids == {"B"} and r.attribution == {"C": "A"}


def test_req_det_2_4_an_open_earlier_copy_still_makes_the_later_copy_a_mirror():
    """REQ-DET-2.4: the pair is one report whether or not the earlier copy has closed."""
    r = detect([mk("O", 0), mk("N", 0, 5, system="new", open_hours=1)])
    assert r.mirror_ids == {"N"} and r.incidents == []


def test_req_det_2_4_same_system_fast_re_report_is_a_zombie():
    """REQ-DET-2.4: closed 1 h after opening, re-reported 5 h after the original opened, same system."""
    z = zs([mk("A", 0, 0, close_hours=1), mk("B", 0, open_hours=5)])
    assert "A" in z


def test_req_det_2_4_cross_system_pair_after_six_hours_is_a_zombie():
    """REQ-DET-2.4: the mirror window is 6 h; beyond it, a cross-system re-report is a normal one."""
    assert "A" in zs([mk("A", 0, 0, close_hours=1), mk("N", 0, system="new", open_hours=7)])


def test_req_det_2_4_a_closed_mirror_copy_is_never_an_original():
    """ZD step 9 (ops#30, supersedes clarification S14): the later copy is never an original, so a later report resurrects
    only the earlier copy's incident."""
    cs = [mk("A", 0, 0, close_hours=1), mk("N", 0, 2, system="new", open_hours=3), mk("R", 10, system="new")]
    assert list(zs(cs)) == ["A"]
    assert detect(cs).zombies[0].reports_after == 1


def test_req_det_2_2_transferred_original_is_never_a_zombie():
    """REQ-DET-2.2: legacy transfer closure text, and the new-system Transitioned code."""
    legacy = mk("A", 0, 1, text="Case Closed. Resubmitted as BCS-00000009", label="referred")
    new = mk("N", 0, 1, system="new", code="Transitioned", label="referred")
    r = detect([legacy, mk("B", 5)])
    assert r.zombies == [] and r.excluded_pairs["transferred_original"] == 1
    r2 = detect([new, mk("M", 5, system="new")])
    assert r2.zombies == [] and r2.excluded_pairs["transferred_original"] == 1


def test_req_det_2_2_noted_new_system_closure_stays_an_original():
    """REQ-DET-2.2: only Transitioned is a transfer; Noted can be resurrected."""
    assert "N" in zs([mk("N", 0, 1, system="new", code="Noted", label="noted"), mk("M", 5, system="new")])


def test_req_det_2_2_one_transferred_member_makes_the_whole_incident_ineligible():
    """REQ-DET-2.2 / step 9: any transferred member -> the incident is never an original."""
    cs = [mk("A", 0, 2), mk("B", 0.5, 2.1, text="transferred to BTD"), mk("R", 9)]
    assert detect(cs).zombies == []


def test_req_det_2_3_a_linked_successor_is_never_a_re_report_of_its_predecessor():
    """REQ-DET-2.3: the catch-all case continues its legacy predecessor."""
    legacy = mk("L", 0, 1)  # an ordinary closure, to isolate the linked-successor rule
    succ = mk("BCS-1", 5, system="new", preds=("L",), catch_all=True)
    r = detect([legacy, succ])
    assert r.zombies == [] and r.excluded_pairs["linked_successor"] == 1


def test_req_det_2_3_a_linked_successor_can_still_resurrect_a_different_original():
    """REQ-DET-2.3: only its own predecessor's incident is excluded."""
    cs = [mk("L", 0, 1, x=0), mk("O", 2, 3, x=5), mk("S", 10, system="new", preds=("L",))]
    r = detect(cs)
    assert r.attribution["S"] == "O" and r.excluded_pairs["linked_successor"] == 1


def test_req_det_2_5_exclusion_counts_cover_every_reason():
    """REQ-DET-2.5: the run report gets a count per reason (zeros included)."""
    assert detect([mk("A", 0, 1)]).excluded_pairs == {"mirror": 0, "transferred_original": 0, "linked_successor": 0}


def test_req_det_2_1_candidate_pairs_are_case_level_and_ordered():
    """REQ-DET-2.1: candidate_pairs lists (original, re-report) with R strictly after the close."""
    cs = [mk("A", 0, 2), mk("B", 5), mk("C", 1.5, 3)]
    assert candidate_pairs(cs) == {("A", "B"), ("C", "B")}
