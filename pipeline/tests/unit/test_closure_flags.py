"""Unit tests for undead311.ingest.closure_flags (REQ-ING-MIRROR)."""

from datetime import UTC, datetime, timedelta

import pytest

from undead311.ingest.closure_flags import MIRROR_WINDOW_HOURS, is_mirror_pair, is_transfer_closure

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
