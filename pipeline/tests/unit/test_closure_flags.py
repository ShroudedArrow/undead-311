"""Unit tests for undead311.ingest.closure_flags (REQ-DET-2.2-2.4, REQ-ING-CATCH)."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from undead311.ingest.closure_flags import (
    MIRROR_WINDOW_HOURS,
    extract_linked_case_id,
    is_mirror_pair,
    is_transfer_closure,
    new_system_closure_label,
    pair_survives,
    resolve_catch_all,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "text",
    [
        "Case Closed Resubmitted as BCS-00231479",
        "See new case BCS-00245470",
        "case transferred to PWD",
        "case migrated to the new system",
        "A new case has been created",
    ],
)
def test_transfer_positive(text):
    assert is_transfer_closure(text)


@pytest.mark.parametrize(
    "text",
    ["Please submit a new case if the problem persists", "Case Resolved", "", None, "open a new case"],
)
def test_transfer_negative(text):
    assert not is_transfer_closure(text)


def test_mirror_window_boundary():
    at = T0 + timedelta(hours=MIRROR_WINDOW_HOURS)
    over = at + timedelta(seconds=1)
    assert is_mirror_pair("legacy", "new", T0, at, True, True)
    assert is_mirror_pair("new", "legacy", at, T0, True, True)
    assert not is_mirror_pair("legacy", "new", T0, over, True, True)


def test_mirror_needs_cross_system_family_and_location():
    assert not is_mirror_pair("legacy", "legacy", T0, T0, True, True)
    assert not is_mirror_pair("legacy", "new", T0, T0, False, True)
    assert not is_mirror_pair("legacy", "new", T0, T0, True, False)


def row(system, open_utc, closure_text=None, closure_code=None, family="pothole_roadway"):
    return {
        "system": system,
        "open_utc": open_utc,
        "type_family": family,
        "closure_text": closure_text,
        "closure_code": closure_code,
    }


CLOSE_AFTER_HOURS = 1


def timeline_pair_survives(original, rereport):
    """pair_survives plus the timeline rule the detector enforces: the re-report must open after the original closed."""
    return rereport["open_utc"] > original["close_utc"] and pair_survives(original, rereport)


@pytest.mark.parametrize("system", ["legacy", "new"])
def test_same_system_fast_rereport_is_candidate(system):
    """REQ-DET-2.2 / REQ-ING-CATCH: original opens T0, closes T0+1h, re-report opens T0+5h (inside the 6 h window), same system: candidate."""
    original = row(system, T0, closure_text="Case Closed", closure_code="Resolved")
    original["close_utc"] = T0 + timedelta(hours=CLOSE_AFTER_HOURS)
    rereport = row(system, T0 + timedelta(hours=5))
    assert rereport["open_utc"] > original["close_utc"]
    assert rereport["open_utc"] - original["open_utc"] <= timedelta(hours=MIRROR_WINDOW_HOURS)
    assert pair_survives(original, rereport)
    assert timeline_pair_survives(original, rereport)
    assert not is_mirror_pair(system, system, original["open_utc"], rereport["open_utc"], True, True)


@pytest.mark.parametrize("system", ["legacy", "new"])
def test_same_system_rereport_before_closure_is_not_candidate(system):
    original = row(system, T0, closure_text="Case Closed", closure_code="Resolved")
    original["close_utc"] = T0 + timedelta(hours=CLOSE_AFTER_HOURS)
    rereport = row(system, T0 + timedelta(minutes=30))
    assert not timeline_pair_survives(original, rereport)


@pytest.mark.parametrize("gap_hours", [0, 5.9])
def test_cross_system_same_timing_rejected(gap_hours):
    original = row("legacy", T0, closure_text="Case Closed")
    rereport = row("new", T0 + timedelta(hours=gap_hours))
    assert not pair_survives(original, rereport)


@pytest.mark.parametrize(
    ("code", "survives"), [("Transitioned", False), ("Noted", True), ("Resolved", True), ("Resolved successfully", True)]
)
def test_new_system_transitioned_never_original(code, survives):
    original = row("new", T0, closure_code=code)
    rereport = row("new", T0 + timedelta(days=3))
    assert pair_survives(original, rereport) is survives


def test_new_system_closure_label_mapping():
    assert new_system_closure_label("Resolved") == "resolved"
    assert new_system_closure_label("Resolved successfully") == "resolved"
    assert new_system_closure_label("Noted") == "noted"
    assert new_system_closure_label("Transitioned") == "referred"
    assert new_system_closure_label("Bogus") is None
    assert new_system_closure_label(None) is None


@given(
    system=st.sampled_from(["legacy", "new"]),
    gap_seconds=st.integers(min_value=-10**7, max_value=10**7),
    same_family=st.booleans(),
    same_location=st.booleans(),
)
def test_same_system_never_mirror(system, gap_seconds, same_family, same_location):
    b = T0 + timedelta(seconds=gap_seconds)
    assert not is_mirror_pair(system, system, T0, b, same_family, same_location)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Resubmitted as BCS-00044034", "BCS-00044034"),
        ("Resubmitted as case BCS-00044024", "BCS-00044024"),
        ("See new case BCS-00264059", "BCS-00264059"),
        ("Please refer to case BCS-00042106 for future inquiries", "BCS-00042106"),
        ("resubmitted as bcs-00044034", "BCS-00044034"),
        ("Closed. Resolved by BCS Contracting", None),
        ("Case closed, work done", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_linked_case_id(text, expected):
    """REQ-DET-2.2 / REQ-ING-CATCH: only transfer closure text yields a link."""
    assert extract_linked_case_id(text) == expected


FAMS = {
    "Request for Pothole Repair": ("pothole_roadway", "core"),
    "Sidewalk Repair (Make Safe)": ("sidewalk", "core"),
    "Traffic Signal Repair": ("traffic_signal", "core"),
    "Graffiti Removal": ("graffiti", "excluded"),
}


def test_resolve_single_core_predecessor_inherits():
    assert resolve_catch_all("streetlight", [("L1", "Request for Pothole Repair")], FAMS) == (
        "pothole_roadway",
        "core",
        ["L1"],
    )


def test_resolve_sidewalk_predecessor():
    assert resolve_catch_all("streetlight", [("L1", "Sidewalk Repair (Make Safe)")], FAMS)[:2] == ("sidewalk", "core")


def test_resolve_excluded_predecessor_stays_excluded():
    assert resolve_catch_all("streetlight", [("L1", "Graffiti Removal")], FAMS)[:2] == ("graffiti", "excluded")


def test_resolve_agreeing_predecessors_inherit():
    preds = [("L2", "Request for Pothole Repair"), ("L1", "Request for Pothole Repair")]
    assert resolve_catch_all("streetlight", preds, FAMS) == ("pothole_roadway", "core", ["L1", "L2"])


def test_resolve_disagreeing_predecessors_sensitivity():
    preds = [("L1", "Graffiti Removal"), ("L2", "Traffic Signal Repair")]
    assert resolve_catch_all("streetlight", preds, FAMS) == ("streetlight", "sensitivity", ["L1", "L2"])


def test_resolve_unlisted_predecessor_type_sensitivity():
    preds = [("L1", "Request for Pothole Repair"), ("L2", "Not A Listed Type")]
    assert resolve_catch_all("streetlight", preds, FAMS)[:2] == ("streetlight", "sensitivity")


def test_resolve_no_link_sensitivity():
    assert resolve_catch_all("streetlight", [], FAMS) == ("streetlight", "sensitivity", [])


def test_linked_successor_is_not_a_rereport_of_its_predecessor():
    """The legacy closure text has no transfer wording here, so only predecessor_ids can reject the pair."""
    orig = {**row("legacy", T0, closure_text="Case Closed"), "id": "L1"}
    succ = {**row("new", T0 + timedelta(days=3), family="pothole_roadway"), "predecessor_ids": ["L1"]}
    assert not pair_survives(orig, succ)


def test_linked_successor_is_candidate_for_a_different_original():
    orig = {**row("legacy", T0, closure_text="Case Closed"), "id": "L9"}
    succ = {**row("new", T0 + timedelta(days=3), family="pothole_roadway"), "predecessor_ids": ["L1"]}
    assert pair_survives(orig, succ)


def test_linked_catch_all_as_original_of_later_rereport():
    orig = {**row("new", T0, closure_text="Done", closure_code="Resolved", family="pothole_roadway"), "id": "N1"}
    orig["predecessor_ids"] = ["L1"]
    later = row("new", T0 + timedelta(days=10), family="pothole_roadway")
    assert pair_survives(orig, later)
