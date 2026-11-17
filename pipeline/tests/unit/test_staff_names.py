"""REQ-ING-PII.6: the run-time staff-name list is built from what the scrub patterns remove, minus street words."""

from __future__ import annotations

import pytest

from undead311.ingest import pii
from undead311.ingest.staff_names import build, harvest_text, read_names, street_words, write_names


@pytest.fixture(autouse=True)
def _no_list_left_behind():
    yield
    pii.set_staff_names([])


@pytest.mark.parametrize(
    "text, names",
    [  # invented names in the shapes the data has
        ("Replaced mantles. A.LOWELL / B.NASH", {"lowell", "nash"}),
        ("Tightened screws. rowan/marsh", {"rowan", "marsh"}),
        ("CHECKED LIGHT  M.LOWELL  D.NASH", {"lowell", "nash"}),
        ("Regards   Kim Ortega  [removed]", {"ortega"}),
        ("Please call Chief Engineer Dana Voss at 5", {"voss"}),
        ("Gale Quill Senior Civil Engineer reviewed it", {"quill"}),
        ("If you have questions. Gale Quill Senior Civil Engineer Boston Public Works", {"quill"}),
        ("patch w/o needed, o/h feed, no names here", set()),
    ],
)
def test_req_ing_pii_6_names_come_from_what_the_patterns_remove(text, names):
    assert harvest_text(text) == names


def test_req_ing_pii_6_street_words_and_rare_tokens_are_dropped():
    """REQ-ING-PII.6: a token that is a street word, or was removed from fewer than 3 cases, is not on the list."""
    texts = [("Done. rowan/marsh", 4), ("Done. lowell/nash", 2), ("Done. quill/lane", 5)]
    streets = street_words(["12 Marsh St", None], None)
    assert streets == {"st", "marsh"} or "marsh" in streets
    assert build(texts, streets) == {"rowan", "quill", "lane"}  # nash/lowell: 2 cases; marsh: a street word


def test_req_ing_pii_6_a_token_that_is_mostly_an_ordinary_word_is_dropped():
    """REQ-ING-PII.6: "grid" signed twice but written thousands of times as a word is not a name."""
    texts = [("Done. rowan/grid", 5), ("The grid was down", 500)]
    assert build(texts, set()) == {"rowan"}


def test_req_ing_pii_6_street_words_read_the_sam_file(tmp_path):
    sam = tmp_path / "s.geojson"
    sam.write_text('{"features":[{"properties":{"ST_NAME":"Vossberg","ALTERNATE_NAME":"Old Quill"}}]}')
    assert {"vossberg", "quill"} <= street_words([], sam)


def test_req_ing_pii_6_listed_names_are_removed_as_standalone_tokens_only():
    """REQ-ING-PII.6: removed wherever they stand alone, never inside another word; off by default; idempotent."""
    text = "Replaced bulb.  Rowan  Marsh.  Rowanberry St, J.ROWAN"
    assert pii.scrub_text(text) == text  # no list loaded
    assert pii.set_staff_names(["rowan", "marsh"]) == 2 and pii.staff_name_count() == 2
    out, counts = pii.scrub(text)
    assert out == "Replaced bulb.  [removed]  [removed].  Rowanberry St, J.[removed]"
    assert counts["staff_name"] == 3
    assert pii.scrub_text(out) == out
    assert pii.scrub_text(text, staff=False) == text


def test_req_ing_pii_6_the_list_is_written_and_read_from_a_file(tmp_path):
    path = tmp_path / "sub" / "staff_names.txt"
    write_names(path, {"b", "a"})
    assert read_names(path) == {"a", "b"} and read_names(tmp_path / "missing.txt") == set()
