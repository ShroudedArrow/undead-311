"""Unit tests for undead311.ingest.closure_flags (REQ-ING-MIRROR)."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from undead311.ingest.closure_flags import (
    MIRROR_WINDOW_HOURS,
    is_mirror_pair,
    is_transfer_closure,
    new_system_closure_label,
    pair_survives,
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


@pytest.mark.parametrize("gap_hours", [0, 5.9])
@pytest.mark.parametrize("system", ["legacy", "new"])
def test_same_system_fast_rereport_is_candidate(system, gap_hours):
    """REQ-ING-MIRROR: closed 1 h after opening, re-reported within the window, same system: still a zombie candidate."""
    original = row(system, T0, closure_text="Case Closed")
    rereport = row(system, T0 + timedelta(hours=gap_hours))
    assert pair_survives(original, rereport)
    assert not is_mirror_pair(system, system, original["open_utc"], rereport["open_utc"], True, True)


def test_same_system_pothole_five_hours_after_original_opened():
    original = row("new", T0, closure_code="Resolved")
    rereport = row("new", T0 + timedelta(hours=5))
    assert pair_survives(original, rereport)


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
