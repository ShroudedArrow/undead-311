"""REQ-SKEP.1-2: Skeptic input selection and objection join."""

from __future__ import annotations

import json

import pytest
from helpers import mk

from undead311.detect.core import detect
from undead311.detect.skeptic import build_input, join_objections, select_for_review, write_input


def town(n=5):
    """n separate places; place i has i+1 re-reports (so reports_after = i+1) plus a closed original."""
    cs = []
    for i in range(n):
        x = 500.0 * i
        cs.append(mk(f"O{i}", 0, 1, x=x))
        cs.extend(mk(f"R{i}_{k}", 5 + k, x=x) for k in range(i + 1))
    return cs


def test_req_skep_1_selection_covers_sample_tour_and_top_reports_without_using_confidence():
    """REQ-SKEP.1: validation + tour + top-N headline by re-report count (ties by ID)."""
    r = detect(town())
    z = {x.incident_id: x.zombie_id for x in r.zombies}
    reasons = select_for_review(r.zombies, validation_ids=[z["O0"]], tour_ids=[z["O1"], "nope:nope"], top_n=2)
    assert reasons == {z["O0"]: ["validation_sample"], z["O1"]: ["judge_tour"], z["O4"]: ["top_reports"],
                       z["O3"]: ["top_reports"]}  # fmt: skip


def test_req_skep_1_top_selection_ignores_confidence_and_non_headline_tiers():
    """REQ-SKEP.1: a high-confidence zombie with fewer re-reports is not picked; sensitivity zombies never are."""
    cs = [mk("A", 0, 1), mk("A1", 5), mk("B", 0, 1, x=500, tier="sensitivity")] + [mk(f"B{k}", 5 + k, x=500) for k in range(4)]
    r = detect(cs)
    assert select_for_review(r.zombies, top_n=1) == {"A:A1": ["top_reports"]}


def test_req_skep_1_input_file_has_scrubbed_case_records_and_is_sorted(tmp_path):
    """REQ-SKEP.1: both case records per item, closure text scrubbed, items sorted by zombie_id."""
    cs = town(3)
    cs[0] = mk("O0", 0, 1, text="Called by Maria Lopez, 617-555-0199")
    r = detect(cs)
    payload = build_input(r.zombies, {c.id: c for c in cs}, "v1", top_n=10)
    ids = [i["zombie_id"] for i in payload["items"]]
    assert ids == sorted(ids) and len(ids) == 3
    text = json.dumps(payload)
    assert "Maria" not in text and "555-0199" not in text and "[removed]" in text
    path = write_input(tmp_path / "p" / "skeptic_input.json", payload)
    assert json.loads(path.read_text())["data_version"] == "v1"


def test_req_skep_2_objections_join_by_incident_and_resurrection_with_not_reviewed_default(tmp_path):
    """REQ-SKEP.2: verdict and notes joined; others stay not_reviewed; the score is recomputed."""
    r = detect(town(2))
    f = tmp_path / "skeptic_objections.json"
    f.write_text(json.dumps([{"incident_id": "O0", "resurrection_id": "R0_0", "verdict": "explained_away",
                              "notes": "Busy corner. Call 617-555-0100."}]))  # fmt: skip
    out = {z.incident_id: z for z in join_objections(r.zombies, f)}
    assert out["O0"].skeptic_verdict == "explained_away" and "555" not in out["O0"].skeptic_notes
    assert out["O1"].skeptic_verdict == "not_reviewed" and out["O1"].confidence_partial
    before = {z.incident_id: z for z in r.zombies}
    assert out["O0"].confidence < before["O0"].confidence


def test_req_skep_2_missing_file_and_bad_verdict(tmp_path):
    """REQ-SKEP.2: no file -> every zombie not_reviewed; an invalid verdict raises."""
    r = detect(town(2))
    assert join_objections(r.zombies, tmp_path / "nope.json") == r.zombies
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"objections": [{"incident_id": "O0", "resurrection_id": "R0_0", "verdict": "maybe"}]}))
    with pytest.raises(ValueError):
        join_objections(r.zombies, bad)
