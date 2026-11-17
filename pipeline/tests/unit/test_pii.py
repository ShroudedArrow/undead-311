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


@pytest.mark.parametrize(
    "text",
    ["Existing Case sent to Parks bcs-00217744", "see Bcs-00340111 and bCs-00912002", "Resubmitted as BCS-00912002"],
)
def test_req_ing_pii_2_bcs_case_ids_are_kept_in_any_letter_case(text):
    """REQ-ING-PII.2: new-system case IDs are kept whether written BCS-, bcs- or mixed case."""
    assert scrub_text(text) == text


def test_req_ing_pii_1_seven_digit_runs_after_a_bcs_word_without_dash_are_removed():
    """REQ-ING-PII.1: only the BCS- prefix (with the dash) protects digits; a 7-digit run could be a local phone number."""
    assert scrub_text("new case bcs 0031234 failed") == "new case bcs [removed] failed"
    assert scrub_text("call 5550123 today") == "call [removed] today"


# REQ-ING-PII.4: staff names in closure notes. The names below are invented; the shapes are the ones the data has.
@pytest.mark.parametrize(
    "text, expected",
    [
        (  # a sign-off phrase and everything after it, the staff signature block included
            (
                "Case Resolved Sidewalk repaired 10/2015 If you feel that this case was closed in error please do not hesitate "
                "to contact me. Pat Rowan Senior Civil Engineer Construction Management Division Boston Public Works [removed]"
            ),
            "Case Resolved Sidewalk repaired 10/2015 If you feel that this case was closed in error [removed]",
        ),
        ("Contractor will patch it. Sincerely  Lee Marsh Supervisor of Utility Coordination", "Contractor will patch it. [removed]"),
        ("Dear Constituent  We sent it to the utility.  Regards   Kim Ortega  [removed]", "Dear Constituent  We sent it to the utility.  [removed]"),
        ("Light replaced.  Thank you  Sam Quill", "Light replaced.  [removed]"),
        ("Thank you for reporting this to the Boston Transportation Department. Thank you Boston 311", None),  # kept
        ("We sincerely apologize for the delay; with regards to the pole, it was replaced.", None),  # sentences, kept
    ],
)
def test_req_ing_pii_4_sign_off_phrase_removes_everything_after_it(text, expected):
    """REQ-ING-PII.4a: "please do not hesitate to contact me", "Sincerely", "Regards" and "Thank you <name>" end the note."""
    out, counts = scrub(text)
    assert out == (expected or text)
    assert bool(counts["signoff"]) == (expected is not None)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Case Resolved twin acorn was turned. w/o completed. rowan/marsh", "Case Resolved twin acorn was turned. w/o completed. [removed]"),
        ("Replaced PHOTO EYE.  Kim/Pat  ", "Replaced PHOTO EYE.  [removed]  "),
        ("MADE SAFE  S.ORTEGA / H.QUILL / J.VOSS / N.RAMIREZ", "MADE SAFE  [removed]"),
        ("INSTALLED POLE  A.Mc DONALD /B.LOWELL / C.NASH", "INSTALLED POLE  [removed]"),
        ("Tightened screws.  Lowell/Nash. 1-20-16 EP", "Tightened screws.  [removed]. 1-20-16 EP"),
        ("CHECKED LIGHT  M.LOWELL  D.NASH", "CHECKED LIGHT  [removed]"),
        ("done  [removed]  / N.Ramirez", "done  [removed]"),
    ],
)
def test_req_ing_pii_4_runs_of_slash_separated_names_or_initials_are_removed(text, expected):
    """REQ-ING-PII.4b: "A.LOWELL / B.NASH"-style initials and "rowan/marsh"-style bare names that end a note go."""
    out, counts = scrub(text)
    assert out == expected
    assert counts["slash_names"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "patch w/o needed, o/h feed, pole w/l.e.d. rectilinear, F/U w/steam, 3/20",
        "roadway/sidewalk repaired; utility/contractor notified; repair/replacement; and/or",
        "see boston.gov/departments/public-works/public-vs-private-ways",
        "no eform/description of issue",
        "owners/managers will be told, tree/branch down",
    ],
)
def test_req_ing_pii_4_ordinary_slashes_are_kept(text):
    """REQ-ING-PII.4b: abbreviations, URLs and word pairs are not names."""
    assert scrub_text(text) == text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Pat Rowan Senior Civil Engineer reviewed it", "[removed] Senior Civil Engineer reviewed it"),
        ("Please call Chief Engineer Kim Ortega at [removed]", "Please call Chief Engineer [removed] at [removed]"),
        ("Lee Marsh Foreman said so; Inspector Quill will visit", "[removed] Foreman said so; Inspector [removed] will visit"),
        ("Contact Director Sam Voss", "Contact Director [removed]"),
        ("The Commissioner Dana Nash agreed", "The Commissioner [removed] agreed"),
    ],
)
def test_req_ing_pii_4_a_name_beside_a_job_title_is_removed_and_the_title_kept(text, expected):
    """REQ-ING-PII.4c: engineer, foreman, supervisor, manager, director, commissioner, inspector and chief."""
    out, counts = scrub(text)
    assert out == expected
    assert counts["name_title"] >= 1


@pytest.mark.parametrize(
    "text",
    [
        "Engineer has been notified. Public Works Construction Inspection Unit (CIU) Inspector states it was patched.",
        "The Boston Public Works Engineer agrees; the Highway Division Manager approved; Street Lighting Inspector responded.",
        "Supervisor of Utility Coordination and Compliance reviewed it",
    ],
)
def test_req_ing_pii_4_titles_without_a_person_are_kept(text):
    """REQ-ING-PII.4c: a job title alone, or beside a department name, is not a name."""
    assert scrub_text(text) == text


def test_req_ing_pii_4_the_new_patterns_are_counted_and_idempotent():
    """REQ-ING-PII.3-4: each new pattern has its own count; a second scrub changes nothing."""
    text = "Fixed.  A.LOWELL / B.NASH  Regards Pat Rowan Chief Engineer"
    once, counts = scrub(text)
    assert once == "Fixed.  [removed]  [removed]"
    assert dict(counts) == {"slash_names": 1, "signoff": 1}
    assert scrub(once)[0] == once
