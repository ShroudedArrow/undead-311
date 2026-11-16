"""REQ-ING-PII.1-3: scrubbing, kept addresses, per-pattern counts."""

from __future__ import annotations

import pytest

from undead311.ingest.pii import PiiCounter, scrub, scrub_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("contact jane.doe@example.com now", "contact [removed] now"),
        ("call (617) 555-0123 please", "call [removed] please"),
        ("call 617-555-0123.", "call [removed]."),
        ("call +1 617 555 0123", "call [removed]"),
        ("local 555-0123 only", "local [removed] only"),
        ("Spoke to Mr. Smith about it", "Spoke to Mr. [removed] about it"),
        ("Dr Jane Doe called", "Dr [removed] called"),
        ("Reported, called by Maria Lopez yesterday", "Reported, called by [removed] yesterday"),
        ("spoke with Pat at the desk", "spoke with [removed] at the desk"),
        ("per John Smith request", "per [removed] request"),
        ("account 12345678 closed", "account [removed] closed"),
    ],
)
def test_req_ing_pii_1_each_pattern(text, expected):
    """REQ-ING-PII.1: emails, phones, honorific names, context names and 7+ digit runs become [removed]."""
    assert scrub_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Pothole at 1312 Boylston St near Washington St & Snow St",
        "INTERSECTION Commonwealth Ave & Exeter St",
        "per request of the city, see notes",
        "Resubmitted as BCS-00912002",
        "closed 2024-03-04 at 14:30:00",
    ],
)
def test_req_ing_pii_2_addresses_streets_and_case_ids_are_kept(text):
    """REQ-ING-PII.2: public case locations and case IDs survive the scrub."""
    assert scrub_text(text) == text


def test_req_ing_pii_3_counts_per_pattern_and_never_the_text():
    """REQ-ING-PII.3: counts per pattern; the removed text appears nowhere in the return value."""
    out, counts = scrub("a@b.com, c@d.org, call 617-555-0123, Mr. Brown, id 99999999")
    assert dict(counts) == {"email": 2, "phone": 1, "honorific_name": 1, "digit_run": 1}
    assert "Brown" not in out and "a@b.com" not in out and "99999999" not in out
    acc = PiiCounter()
    acc.scrub("x@y.io")
    acc.scrub("x@y.io and z@y.io")
    assert acc.counts["email"] == 3


def test_req_ing_pii_1_none_stays_none():
    """REQ-ING-PII.1: missing text is not turned into a string."""
    assert scrub(None)[0] is None


@pytest.mark.parametrize(
    "text",
    [
        "See case #101002227052 for status of the permanent repair",
        "closed as a duplicate of the original's own work order (101002227052).",
        "Duplicate of Existing Case 101005000000",
        "cases 101001241069, 101006699983 and BCS-00340111",
    ],
)
def test_req_ing_pii_2_legacy_case_ids_are_kept(text):
    """REQ-ING-PII.2 (ops#221): legacy case IDs (12 digits starting with 101) are public and kept, like BCS- IDs."""
    assert scrub_text(text) == text
    assert scrub(text)[1] == {}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("call 6175550123 today", "call [removed] today"),  # no separators
        ("call 16175550123 today", "call [removed] today"),
        ("call 617-555-0123 today", "call [removed] today"),
        ("call 617.555.0123 today", "call [removed] today"),
        ("call 617 555 0123 today", "call [removed] today"),
        ("call (617) 555-0123 today", "call [removed] today"),
        ("call +1 617.555.0123 today", "call [removed] today"),
        ("call 555-0123 today", "call [removed] today"),
    ],
)
def test_req_ing_pii_1_phone_numbers_are_removed_with_and_without_separators(text, expected):
    """REQ-ING-PII.1 (ops#221): keeping legacy case IDs does not let a phone number through."""
    assert scrub_text(text) == expected


@pytest.mark.parametrize(
    "run",
    ["1234567", "12345678", "123456789", "1010022", "10100222705", "99999999999"],  # 7 to 11 digits
)
def test_req_ing_pii_1_other_7_to_11_digit_runs_are_removed(run):
    """REQ-ING-PII.1 (ops#221): 7 to 11 digit runs are removed, even when they start with 101."""
    assert scrub_text(f"ref {run} end") == "ref [removed] end"


@pytest.mark.parametrize(
    "run",
    ["201002227052", "100002227052", "1010022270521", "10100222705212345"],
)
def test_req_ing_pii_1_only_exact_legacy_case_ids_are_kept(run):
    """REQ-ING-PII.1 (ops#221): a 12-digit run not starting with 101, or a longer run starting with 101, is removed."""
    assert scrub_text(f"ref {run} end") == "ref [removed] end"
