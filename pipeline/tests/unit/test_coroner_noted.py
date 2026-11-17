"""REQ-COR-NOTED: "Case Noted" closures stay noted unless the text affirms completed work with no negation, hand-off or
temporary cue; sign-offs are cut before matching; the label table is rechecked for these texts."""

from __future__ import annotations

import pytest

from undead311.coroner.join import assign_label_source
from undead311.coroner.phrases import is_noted_lead, phrase_label
from undead311.coroner.templates import mask_template


def label(text: str) -> str | None:
    return phrase_label(mask_template(f"Case Closed. Closed date : 2024-05-01 10:00:00.1 Case Noted {text}"))


@pytest.mark.parametrize(
    "text, expected",
    [
        # completed work, no cue: the only way a "Case Noted" text becomes resolved
        ("The sidewalk at this address has been repaired.", "resolved"),
        ("pothole patched", "resolved"),
        # no completed-work word: noted
        ("photos were taken for the file", "noted"),
        # hand-off cues: referred
        ("The Utility and contractor has been notified", "referred"),
        ("This is a private driveway owner responsibility thank you", "referred"),
        ("Eversource crews removed the post and replaced the fixture", "referred"),
        ("Service request was created. A new service request has been created for the owner.", "referred"),
        # temporary cues: made_safe_temporary
        ("Put cones there and sent down to be cut out", "made_safe_temporary"),
        ("We put a cone there for now, the pothole was filled for the time being", "made_safe_temporary"),
        ("Pacella covered the sinkhole with a metal plate", "made_safe_temporary"),
        ("picked up sign", "made_safe_temporary"),  # spot-check row 3 (owner review 2026-11-17)
        # negation cues: noted
        ("Potholes were filled. Roadway needs to be resurfaced, will visit again", "noted"),
        ("This job is not necessary, the pole was replaced last year", "noted"),
        ("No pole found; replaced the lamp anyway", "noted"),
        ("The work was not completed", "noted"),
        # the location cannot be found: invalid
        ("Unable to locate complaint location. Please provide a better location", "invalid"),
        ("Multiple potholes filled. Could not locate the address, need a better location", "invalid"),
    ],
)
def test_req_cor_noted_2_to_4_cues_decide_the_label_of_a_case_noted_text(text, expected):
    """REQ-COR-NOTED.2-4: completed work resolves a "Case Noted" text only when no negation, hand-off or temporary cue is
    present; each cue maps to its label; a location that cannot be found is invalid."""
    assert label(text) == expected


def test_req_cor_noted_2_an_inspection_is_not_completed_work():
    """REQ-COR-NOTED.2: "visual inspection completed" is not a repair."""
    assert label("Visual inspection completed, location verified, signage posted") == "noted"


def test_req_cor_noted_3_a_negated_temporary_cue_is_not_a_cue():
    """REQ-COR-NOTED.3: "no cone found" and "the plate is neither banging nor loose" do not mean made safe."""
    assert label("No cone found") == "noted"
    assert label("After inspection the plate is neither banging nor loose") == "noted"
    assert label("The root plate shows no sign of movement") == "noted"


@pytest.mark.parametrize(
    "text, expected",
    [
        # the sign-off and signature are cut before matching: a utility in a signature, or "removed" in a marker, is no cue
        ("The pole was repaired. Regards, Pat Rowan, Eversource liaison, cones available on request", "resolved"),
        ("The sidewalk was repaired. Sincerely Pat Rowan [removed]", "resolved"),
        ("The sidewalk was repaired. If you have any further questions please call BWSC at the number listed below", "resolved"),
        ("The sign was reset. Please do not hesitate to contact me. Pat Rowan, Foreman, National Grid contractor", "resolved"),
        ("The pole was repaired. Thank you Kim Ortega", "resolved"),
        # a sentence is not a sign-off
        ("We sincerely apologize; Eversource has been notified", "referred"),
    ],
)
def test_req_cor_noted_5_signatures_and_sign_offs_cannot_trigger_cues(text, expected):
    """REQ-COR-NOTED.5: sign-off text and the signature below it are cut before any cue is matched."""
    assert label(text) == expected


def test_req_cor_noted_5_a_scrub_marker_is_not_work_wording():
    """REQ-COR-NOTED.5: "[removed]" (a scrubbed name) must not read as the work word "removed"."""
    assert label("The picture and the address do not match. [removed]") == "invalid"


def test_req_cor_noted_1_only_case_noted_texts_use_the_rule():
    """REQ-COR-NOTED.1: "Case Resolved" texts keep the general rule, and the lead word is found after the boilerplate."""
    assert is_noted_lead(mask_template("Case Closed. Closed date : 2024-05-01 10:00:00.1 Case Noted picked up sign"))
    assert is_noted_lead(mask_template("Case Closed Case Noted"))
    assert not is_noted_lead(mask_template("Case Closed. Closed date : 2024-05-01 10:00:00.1 Case Resolved picked up sign"))
    assert phrase_label(mask_template("Case Closed Case Resolved hole made safe")) == "made_safe_temporary"


def test_req_cor_noted_6_the_label_table_is_rechecked_only_by_cues():
    """REQ-COR-NOTED.6: a table label of resolved or noted moves when a cue is present; with no cue the table label stands;
    every other table label stays."""
    noted_work = mask_template("Case Closed Case Noted Contractor has been notified")
    assert assign_label_source("legacy", None, noted_work, {noted_work: "resolved"})[::2] == ("referred", "noted_rule")
    assert assign_label_source("legacy", None, noted_work, {noted_work: "noted"})[::2] == ("referred", "noted_rule")
    plain = mask_template("Case Closed Case Noted repairs have been made")
    assert assign_label_source("legacy", None, plain, {plain: "resolved"})[::2] == ("resolved", "table")
    dup = mask_template("Case Closed Case Noted Contractor has been notified")
    assert assign_label_source("legacy", None, dup, {dup: "duplicate"})[::2] == ("duplicate", "table")
    other = mask_template("Case Closed Case Resolved Contractor has been notified")
    assert assign_label_source("legacy", None, other, {other: "resolved"})[::2] == ("resolved", "table")


def test_req_cor_noted_6_a_transitioned_code_still_wins():
    """REQ-COR-1.2: the new-system Transitioned code is `referred` before any table or Case Noted rule."""
    noted_work = mask_template("Case Closed Case Noted The sidewalk was repaired")
    assert assign_label_source("new", "Transitioned", noted_work, {noted_work: "resolved"})[::2] == ("referred", "code")
