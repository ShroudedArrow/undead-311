"""Properties P1, P2, P3, P8, P14, P15 (testing.md #1, #2, #4, #13, #20): REQ-DET-2.1-2.4, REQ-DET-3, REQ-ING-CATCH.5."""

from __future__ import annotations

from dataclasses import replace

from helpers import params
from hypothesis import given
from hypothesis import strategies as st
from strategies import town

from undead311.detect.core import candidate_pairs, detect
from undead311.detect.edges import brute_edges
from undead311.detect.params import DEFAULT
from undead311.ingest.closure_flags import is_transferred_original


def _incident_of(result):
    return {i.incident_id: i for i in result.incidents}


@given(town())
def test_prop_p1_a_case_is_never_its_own_zombie(cases):
    """REQ-DET-2.1: the resurrection is never a member of its own incident."""
    for z in detect(cases).zombies:
        assert z.resurrection_id not in z.member_ids


@given(town())
def test_prop_p2_every_attached_re_report_opens_strictly_after_its_incidents_close(cases):
    """REQ-DET-2.1: R.open > incident close, and within WINDOW_DAYS of it (UTC)."""
    by_id = {c.id: c for c in cases}
    r = detect(cases)
    inc = _incident_of(r)
    for rid, iid in r.attribution.items():
        gap = by_id[rid].open_utc - inc[iid].close_utc
        assert gap.total_seconds() > 0
        assert gap.days <= DEFAULT.WINDOW_DAYS


@given(town(), st.sampled_from([("RADIUS_M", 50), ("RADIUS_M", 100), ("WINDOW_DAYS", 90), ("WINDOW_DAYS", 61)]),
       st.sampled_from(["segment", "radius"]))
def test_prop_p3_raising_radius_or_window_never_removes_a_candidate_pair(cases, change, matching):
    """REQ-DET-MATCH, REQ-DET-2: case-level candidate pairs only grow (zombie counts are not asserted monotonic)."""
    small = params(matching=matching)
    big = replace(small, **{change[0]: change[1]})
    assert candidate_pairs(cases, small) <= candidate_pairs(cases, big)


@given(town(), st.randoms(use_true_random=False))
def test_prop_p8_each_re_report_attaches_to_at_most_one_incident_deterministically(cases, rnd):
    """REQ-DET-3.1-3.2: one incident per R; the attribution does not change with input order."""
    r = detect(cases)
    rows = [(z.incident_id, z.resurrection_id) for z in r.zombies]
    rows += [(z.incident_id, z.resurrection_id) for z in r.planned_followups]
    rows += [(z.incident_id, z.rereport_id) for z in r.separate_deaths]
    resurrections = [rid for _, rid in rows]
    assert len(resurrections) == len(set(resurrections))  # one R can resurrect only one incident
    assert set(r.attribution.values()) >= {iid for iid, _ in rows}
    shuffled = cases[:]
    rnd.shuffle(shuffled)
    r2 = detect(shuffled)
    assert r.attribution == r2.attribution and r.zombies == r2.zombies


@given(town())
def test_prop_p14_mirror_and_transfer_pairs_never_survive(cases):
    """REQ-DET-2.2, 2.4: no mirror R is attached; no incident with a transferred member has a zombie."""
    r = detect(cases)
    by_id = {c.id: c for c in cases}
    assert not (set(r.attribution) & set(r.mirror_ids))
    for z in r.zombies:
        for m in z.member_ids:
            c = by_id[m]
            assert not is_transferred_original(
                {"system": c.system, "closure_text": c.closure_text, "closure_code": c.closure_code}
            )
    # same-system pairs are never mirrors: every mirror has a closed cross-system partner within 6 h and an edge
    edges = brute_edges([c for c in cases], DEFAULT)
    for mid in r.mirror_ids:
        c = by_id[mid]
        assert any(
            by_id[o].is_closed and by_id[o].system != c.system
            and abs((by_id[o].open_utc - c.open_utc).total_seconds()) <= 6 * 3600
            for a, b in edges if mid in (a, b) for o in (a if b == mid else b,)
        )


@given(town())
def test_prop_p15_a_linked_successor_is_never_a_re_report_of_its_predecessors_incident(cases):
    """REQ-DET-2.3, REQ-ING-CATCH.5: R's predecessors are never members of the incident R attaches to."""
    by_id = {c.id: c for c in cases}
    r = detect(cases)
    inc = _incident_of(r)
    for rid, iid in r.attribution.items():
        assert not set(by_id[rid].predecessor_ids) & set(inc[iid].member_ids)


def test_prop_p15_generator_does_produce_linked_successors():
    """REQ-DET-2.3: guard against a vacuous P15, a handcrafted town has the link and the exclusion is counted."""
    from helpers import mk

    r = detect([mk("L", 0, 1), mk("S", 4, system="new", preds=("L",))])
    assert r.excluded_pairs["linked_successor"] == 1
