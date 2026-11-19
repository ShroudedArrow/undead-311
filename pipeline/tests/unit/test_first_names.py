"""REQ-ING-PII.7: first-name rules for staff names in the middle of a note. All names below are invented."""

from __future__ import annotations

import pytest

from undead311.ingest import first_names as fn
from undead311.ingest.pii import REMOVED, scrub, scrub_text


@pytest.fixture(autouse=True)
def _static_places_only():
    fn.set_place_words([])
    yield
    fn.set_place_words([])


def test_req_ing_pii_7_the_first_name_list_is_a_sourced_data_file():
    """REQ-ING-PII.7: 2,000 lower-case names, most common first, with the SSA source in the header."""
    lines = fn.NAMES_FILE.read_text(encoding="utf-8").splitlines()
    header = [ln for ln in lines if ln.startswith("#")]
    names = [ln for ln in lines if ln and not ln.startswith("#")]
    assert any("Social Security Administration" in ln for ln in header) and any(
        "ssa.gov" in ln for ln in header
    )
    assert len(names) == len(set(names)) == 2000
    assert all(n == n.lower() and n.isalpha() and len(n) >= 3 for n in names)
    assert {"michael", "mary", "john"} <= set(names[:50])
    assert fn.first_names() == frozenset(names)


@pytest.mark.parametrize(
    "text, expected",
    [  # rule (a): a listed first name and a second capitalized word
        ("Spoke to Gerald Pennywhistle about it.", f"Spoke to {REMOVED} about it."),
        (
            "Case Noted. Please contact Dana Quillfeather for details.",
            f"Case Noted. Please contact {REMOVED} for details.",
        ),
        (
            "Call Mary Ann Zeller.",
            f"Call {REMOVED} Zeller.",
        ),  # "Mary Ann": the first pair; a third word is not chased
        ("Work done by Peter O'Rourke today", f"Work done by {REMOVED} today"),
        ("Checked by Brian McTavish", f"Checked by {REMOVED}"),
    ],
)
def test_req_ing_pii_7a_two_word_names_are_removed(text, expected):
    assert scrub_text(text, staff=False) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Washington St",
        "Columbus Ave",
        "Warren Street near Franklin Park",
        "Dudley Square",
        "Charles River Dam",
        "Martin Luther King Blvd",
        "Paul Revere Mall",
        "Jackson Sq station",
        "Dean Road",
        "Kelly Rink",
        "Hyde Park Ave",
        "Jamaica Plain",
        "Charles Circle",
        "Lewis Wharf",
        "Arthur Fiedler Footbridge",
        "Franklin Hill Ave",
        "Carter Playground",
        "George Washington Way",
        "Everett St",
        "Quincy Massachusetts",
        "Chelsea Street Bridge",
    ],
)
def test_req_ing_pii_7a_streets_and_known_places_are_kept(text):
    """REQ-ING-PII.7: a street suffix, street word or known place after a first name keeps the pair."""
    assert scrub_text(f"Pothole at {text} fixed", staff=False) == f"Pothole at {text} fixed"


def test_req_ing_pii_7a_run_time_street_words_keep_a_street_that_the_static_lists_do_not_know():
    text = "Fixed at Gerald Pennywhistle"  # invented street name, no suffix
    assert scrub_text(text, staff=False) == f"Fixed at {REMOVED}"
    assert fn.set_place_words(["Pennywhistle", "Quillfeather"]) == 2
    assert scrub_text(text, staff=False) == text


@pytest.mark.parametrize(
    "text",
    [
        "Will Follow up next week",
        "Mark Resolved",
        "Carmen Sent a note",
        "Alexander Inspected the pole",
        "Cassidy Landscaping",
        "Riley Brothers paved it",
        "Kennedy Director",
        "John This is done",
        "Case Closed",
        "Thank you",
        "Boston Public Works",
        "National Grid",
        "Lane Must",
        "Dennis Patch",
    ],
)
def test_req_ing_pii_7a_ordinary_words_after_a_name_like_word_are_kept(text):
    """REQ-ING-PII.7: note words, business words, verbs and ambiguous first words do not trigger rule (a)."""
    assert scrub_text(text, staff=False) == text


def test_req_ing_pii_7a_needs_two_adjacent_capitalized_words():
    for text in ("mark twain", "Mark, Twain", "MARK TWAIN", "Mark   twain", "john. Smith"):
        assert scrub_text(text, staff=False) == text, text


@pytest.mark.parametrize(
    "text, expected",
    [  # rule (b): the first name goes, "from" and the organization stay
        ("Met with Dana from National Grid at 11.", f"Met with {REMOVED} from National Grid at 11."),
        ("Case Resolved Peter from BWSC called back", f"Case Resolved {REMOVED} from BWSC called back"),
        ("Tom from Eversource.", f"{REMOVED} from Eversource."),
    ],
)
def test_req_ing_pii_7b_first_name_from_organization(text, expected):
    out, counts = scrub(text, staff=False)
    assert out == expected
    assert counts["first_name_from"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "Dana from the state",
        "Received from National Grid",
        "Sidewalk from Dana",
        "Hope from Eversource",
        "Dana from",
    ],
)
def test_req_ing_pii_7b_needs_a_listed_first_name_and_a_capitalized_organization(text):
    assert scrub_text(text, staff=False) == text


@pytest.mark.parametrize(
    "text, expected",
    [  # rule (c): the place after "@" stays
        ("Gerald Pennywhistle @ Blue Hill Ave", f"{REMOVED} @ Blue Hill Ave"),
        (
            "Please call Dana Quillfeather @ the yard on Tremont St",
            f"Please call {REMOVED} @ the yard on Tremont St",
        ),
        (
            "Brian Warren @ City Hall Plaza",
            f"{REMOVED} @ City Hall Plaza",
        ),  # "Warren" is a street word, kept only without "@"
        ("Crew Gerald Pennywhistle@ 5pm", f"Crew {REMOVED}@ 5pm"),
    ],
)
def test_req_ing_pii_7c_name_at_place_keeps_the_place(text, expected):
    fn.set_place_words(["warren"])
    out, counts = scrub(text, staff=False)
    assert out == expected
    assert counts["name_at"] == 1 and counts["first_name"] == 0


def test_req_ing_pii_7c_a_street_before_the_at_sign_is_kept():
    assert scrub_text("Washington St @ Mass Ave", staff=False) == "Washington St @ Mass Ave"
    assert scrub_text("Columbus Ave @ Ruggles", staff=False) == "Columbus Ave @ Ruggles"


def test_req_ing_pii_7_counts_are_per_rule_and_the_scrub_is_idempotent():
    text = "Met Dana from National Grid and Gerald Pennywhistle @ Tremont St, also Peter Quillfeather."
    out, counts = scrub(text, staff=False)
    assert counts["first_name_from"] == 1 and counts["name_at"] == 1 and counts["first_name"] == 1
    assert "Dana" not in out and "Pennywhistle" not in out and "Quillfeather" not in out
    assert "National Grid" in out and "Tremont St" in out
    assert scrub_text(out, staff=False) == out


def test_req_ing_pii_7_runs_with_the_other_patterns_and_the_staff_list():
    text = "Gerald Pennywhistle @ 617-555-0123 and Zed Voss"
    assert scrub_text(text, staff=False) == f"{REMOVED} @ {REMOVED} and Zed Voss"


def test_req_ing_pii_7_never_returns_the_removed_text_in_counts():
    _, counts = scrub("Gerald Pennywhistle @ Tremont St", staff=False)
    assert all(isinstance(k, str) and "Pennywhistle" not in k for k in counts)


@pytest.mark.parametrize(
    "text, expected",
    [  # a listed first name directly beside [removed], on either side
        ("Contact Gerald [removed] today", f"Contact {REMOVED} {REMOVED} today"),
        ("Contact [removed] Gerald today", f"Contact {REMOVED} {REMOVED} today"),
        ("Signed Dana [removed]", f"Signed {REMOVED} {REMOVED}"),
        ("Signed [removed] Dana", f"Signed {REMOVED} {REMOVED}"),
        ("Gerald\n[removed]", f"{REMOVED}\n{REMOVED}"),
    ],
)
def test_req_ing_pii_7d_a_first_name_beside_removed_is_removed(text, expected):
    out, counts = scrub(text, staff=False)
    assert out == expected
    assert counts["first_name_beside_removed"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "Will [removed] follow",
        "Case Resolved [removed]",
        "Gerald, [removed]",
        "Gerald removed",
        "[removed] gerald",
        "Gerald and [removed]",
        "[removed] Hope",
        "Boston [removed]",
    ],
)
def test_req_ing_pii_7d_other_neighbours_are_kept(text):
    """REQ-ING-PII.7: only a capitalized listed name that is not an ordinary word, with white space only between."""
    assert scrub_text(text, staff=False) == text


@pytest.mark.parametrize(
    "text, expected",
    [  # a listed first name and one capital initial, with or without the period
        ("Called Gerald S. about it", f"Called {REMOVED}. about it"),
        ("Called Gerald S about it", f"Called {REMOVED} about it"),
        ("Signed Dana Q.", f"Signed {REMOVED}."),
        ("Signed Dana Q", f"Signed {REMOVED}"),
        ("Signed Dana Q. Pennywhistle done", f"Signed {REMOVED} done"),  # a surname after the period goes too
    ],
)
def test_req_ing_pii_7e_first_name_and_a_single_initial_are_removed(text, expected):
    out, counts = scrub(text, staff=False)
    assert out == expected
    assert counts["first_name_initial"] == 1


@pytest.mark.parametrize(
    "text",
    ["Gerald SW corner", "Gerald s.", "Gerald ST", "Gerald S.W. corner", "Will S. said", "Gerald 5 poles"],
)
def test_req_ing_pii_7e_not_an_initial_not_removed(text):
    """REQ-ING-PII.7: two capitals, a lower-case letter, a dotted direction, a digit or an ambiguous first word."""
    assert scrub_text(text, staff=False) == text


def test_req_ing_pii_7d_a_name_beside_a_removal_made_in_the_same_pass_is_removed_and_the_result_is_stable():
    """REQ-ING-PII.7: "Van" is a street word of the run, so "Van Scoy" goes first and leaves "Gerald [removed]"; a second
    pass takes Gerald."""
    fn.set_place_words(["van"])
    out, counts = scrub("Signed Gerald Van Scoy today", staff=False)
    assert out == f"Signed {REMOVED} {REMOVED} today"
    assert counts["first_name"] == 1 and counts["first_name_beside_removed"] == 1
    assert scrub_text(out, staff=False) == out


@pytest.mark.parametrize(
    "text",
    [
        "Pothole at 46 Patrick J Lydon Way",
        "William F McClellan Hwy",
        "Malcolm X Blvd",
        "Malcolm X",
        "Richard B. Ross Way",
        "John A. Andrew St",
        "George R. Visconti Rd",
        "Leo M Birmingham Pkwy",
        "Albert A. Jacobbe Rd",
    ],
)
def test_req_ing_pii_7e_street_names_with_a_middle_initial_are_kept(text):
    """REQ-ING-PII.7: a street suffix, known place or run street word after the initial keeps the street."""
    fn.set_place_words(["lydon", "mcclellan", "visconti", "birmingham", "jacobbe", "ross"])
    assert scrub_text(text, staff=False) == text
