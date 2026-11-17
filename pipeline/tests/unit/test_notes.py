"""REQ-ING-PII.5: a closure note is shown only when at least 5 closed cases share its scrubbed text."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from undead311.export.notes import MIN_NOTE_CASES, note_counts, note_key, shown_note


def test_req_ing_pii_5_threshold_is_five():
    assert MIN_NOTE_CASES == 5


def test_req_ing_pii_5_dates_and_numbers_do_not_split_a_note():
    """REQ-ING-PII.5: texts that differ only in the closing time or a number are one note."""
    texts = [f"Case Closed. Closed date : 2024-0{i}-01 08:00:00.1 Case Resolved Pothole {i} filled" for i in range(1, 6)]
    counts = note_counts(texts)
    assert len(counts) == 1 and next(iter(counts.values())) == 5
    assert shown_note(texts[0], counts) == (texts[0], False)


def test_req_ing_pii_5_four_cases_are_not_enough():
    texts = ["Case Closed Case Resolved Replaced photo eye. Done by the night crew"] * 4
    assert shown_note(texts[0], note_counts(texts)) == (None, True)
    assert shown_note(texts[0], note_counts(texts * 2)) == (texts[0], False)


def test_req_ing_pii_5_missing_and_empty_notes_are_not_hidden():
    counts = note_counts([None, "", "   "])
    assert not counts
    assert shown_note(None, counts) == (None, False)
    assert shown_note("", counts) == (None, False)


def test_req_ing_pii_5_the_shown_text_is_scrubbed():
    """REQ-ING-PII.5: counting and showing both use the scrubbed text."""
    text = "Case Resolved Fixed. Call 617-555-0100"
    counts = note_counts([text] * 5)
    assert note_key(text) == "case resolved fixed. call [removed]"
    assert shown_note(text, counts) == ("Case Resolved Fixed. Call [removed]", False)


@given(st.text(max_size=80), st.integers(0, 4))
def test_prop_req_ing_pii_5_a_note_seen_fewer_than_five_times_is_never_shown(text, copies):
    """REQ-ING-PII.5: for any text, fewer than 5 closed cases means no text is exported."""
    counts = note_counts([text] * copies)
    shown, _hidden = shown_note(text, counts)
    key = note_key(text)
    assert shown is None or not key
