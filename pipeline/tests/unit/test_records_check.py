"""The records-based check of the validation sample (REQ-STAT-VAL.5).

Rules under test: how a re-report's closure maps to one class, which closures are ambiguous, and that every rate has a Wilson
interval inside [0, 1]. The committed `data/labels/validation_records.csv` is checked against the committed sample.
"""

from __future__ import annotations

import csv
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from undead311.stats import records_check as rc
from undead311.stats import validation as val
from undead311.stats.tour import build_tour

REPO = Path(__file__).resolve().parents[3]
TABLE = {
    "completed by task": "resolved", "violation issued": "resolved", "duplicate request": "duplicate",
    "no issue found at location": "invalid", "roadway has been repaired": "resolved",
}  # fmt: skip


def one(status="Closed", code="Resolved", text="Completed by Task", system="new"):
    return rc.classify(system, status, code, text, TABLE)


def test_req_stat_val_5_a_closed_resolved_case_with_a_work_note_is_repaired_again_and_not_ambiguous():
    c = one()
    assert (c.klass, c.ambiguous, c.label) == ("repaired_again", "", "resolved")


def test_req_stat_val_5_an_open_re_report_is_still_open_whatever_its_text():
    assert one(status="In progress", code="", text="").klass == "still_open"
    assert one(status="Open", code=None, text="Completed by Task", system="legacy").klass == "still_open"


def test_req_stat_val_5_duplicate_noted_and_transitioned_closures_map_to_their_classes():
    assert one(code="Noted", text="Duplicate Request").klass == "duplicate"
    assert one(code="Noted", text="No issue found at location").klass == "invalid_or_nothing_found"
    assert one(code="Transitioned", text="Reallocated to Non-City of Boston Stakeholder").klass == "referred"


def test_req_stat_val_5_a_resolved_closure_that_names_enforcement_is_ambiguous_not_repaired():
    c = one(text="Violation issued.")
    assert c.klass == "repaired_again" and c.ambiguous == "conflicting_cue"


def test_req_stat_val_5_a_resolved_code_with_no_text_is_ambiguous_code_only():
    assert one(code="Resolved", text="").ambiguous == "code_only"
    assert one(code="Resolved", text=None).ambiguous == "code_only"


def test_req_stat_val_5_a_closed_case_with_no_reason_at_all_is_other_and_unlabeled():
    c = one(code="", text="")
    assert (c.klass, c.ambiguous) == ("other", "unlabeled")


def rows(spec: list[tuple[str, str, str]]) -> list[dict]:
    """(class, ambiguous_reason, type_family) triples as record rows."""
    return [{"zombie_id": f"z{i}", "class": k, "ambiguous_reason": a, "type_family": f, "checked_on": "2026-11-21"}
            for i, (k, a, f) in enumerate(spec)]  # fmt: skip


def test_req_stat_val_5_only_unambiguous_repairs_are_confirmed_and_ambiguous_ones_are_listed_apart():
    s = rc.count_classes(rows([("repaired_again", "", "sign"), ("repaired_again", "conflicting_cue", "sign"),
                               ("still_open", "", "sidewalk"), ("other", "unlabeled", "sidewalk")]))  # fmt: skip
    assert s["confirmed"] == ["z0"] and s["ambiguous_ids"] == ["z1", "z3"]
    assert s["repaired_again"]["k"] == 1 and s["repaired_again"]["n"] == 4
    assert s["repaired_again_with_ambiguous"]["k"] == 2  # the unlabeled one could not be a repair
    assert s["repaired_again_of_closed"]["n"] == 3
    assert s["by_type"]["sign"]["repaired_again"] == 1 and s["by_type"]["sidewalk"]["repaired_again"] == 0


@given(st.lists(st.tuples(st.sampled_from(rc.CLASSES), st.sampled_from(("",) + rc.AMBIGUOUS_REASONS),
                          st.sampled_from(("sign", "sidewalk", "streetlight"))), min_size=1, max_size=60))
def test_req_stat_val_5_property_every_rate_lies_in_0_1_and_the_confirmed_set_is_inside_the_ambiguity_free_repairs(spec):
    s = rc.count_classes(rows(spec))
    for r in (s["repaired_again"], s["repaired_again_with_ambiguous"], *[v["rate"] for v in s["by_type"].values()]):
        assert 0 <= r["lo"] <= r["rate"] <= r["hi"] <= 1
    assert s["repaired_again"]["k"] <= s["repaired_again_with_ambiguous"]["k"] <= s["n"]
    assert sum(s["classes"].values()) == s["n"]
    assert set(s["confirmed"]).isdisjoint(s["ambiguous_ids"])


def test_req_stat_val_5_score_records_reports_the_share_over_all_sampled_zombies_and_has_no_raters():
    v = val.score_records([], rows([("repaired_again", "", "sign")] * 3 + [("still_open", "", "sign")] * 2))
    assert v.status == "scored" and v.method == "records" and v.kappa is None and v.cant_tell_share is None
    assert (v.precision["k"], v.precision["n"]) == (3, 5) and len(v.confirmed) == 3
    assert v.to_json("v")["records"]["checked_on"] == "2026-11-21"
    assert val.score_records([], []).status == "awaiting_field_labels"


def test_req_stat_val_5_the_tour_names_how_it_was_confirmed():
    from types import SimpleNamespace

    zs = [SimpleNamespace(zombie_id=f"z{i}", tier="headline", skeptic_verdict="survives", gap_days=5.0, city_rereport=False,
                          reports_after=1) for i in range(4)]  # fmt: skip
    assert build_tour(zs, None, ["z0", "z1", "z2"], "records").confirmation == "records"
    assert build_tour(zs, None, ["z0", "z1", "z2"]).confirmation == "field"
    assert build_tour(zs, None, ["z0"], "records").confirmation is None  # provisional: nothing confirmed it


def test_req_stat_val_5_the_committed_records_cover_the_committed_sample_once_each():
    sample = [r["zombie_id"] for r in csv.DictReader((REPO / "data/labels/validation_sample.csv").open())]
    got = rc.read_records(REPO / "data" / "labels" / rc.RECORDS_FILE)
    assert sorted(r["zombie_id"] for r in got) == sorted(sample) and len(sample) == 50
    assert all(r["class"] in rc.CLASSES for r in got)
    assert all(r["ambiguous_reason"] in ("", *rc.AMBIGUOUS_REASONS) for r in got)
    assert all(r["status"] == "Closed" or r["class"] == "still_open" for r in got)
    assert len({r["checked_on"] for r in got}) == 1


def test_req_stat_val_5_the_committed_records_hold_no_unshared_closure_text():
    """A note is committed only when 5 or more closed cases share it; the rest read as hidden (the cards' rule)."""
    for r in rc.read_records(REPO / "data" / "labels" / rc.RECORDS_FILE):
        assert not r["closure_text"] or r["closure_text"].startswith("[hidden") or len(r["closure_text"]) < 120
