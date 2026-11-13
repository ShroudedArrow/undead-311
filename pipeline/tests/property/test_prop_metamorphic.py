"""Properties P9, P10 and P4 part 2 (testing.md #14, #15, #5): metamorphic and order invariance of detection."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st
from strategies import town

from undead311.detect.core import detect


def brief(cases):
    return [(c.id, c.system[0], c.type_family[:3], c.open_utc.strftime("%d %H"),
             c.close_utc and c.close_utc.strftime("%d %H"), c.coroner_label, c.scope_tier[0], c.source[:4],
             c.closure_code, bool(c.closure_text), c.city_originated_type, c.lon) for c in cases]  # fmt: skip


def tier_counts(result):
    return (result.count("headline"), result.count("source_unknown"), result.count("sensitivity"),
            len(result.planned_followups), len(result.separate_deaths))  # fmt: skip


@given(town(), st.floats(-0.002, 0.002), st.floats(-0.002, 0.002))
def test_prop_p9_translating_every_case_by_the_same_offset_keeps_counts(cases, dlat, dlon):
    """REQ-DET-1, 2, 3 (testing.md #14): a uniform small translation leaves counts per tier unchanged."""
    moved = [replace(c, lat=c.lat + dlat, lon=c.lon + dlon) for c in cases]
    assert tier_counts(detect(cases)) == tier_counts(detect(moved))


@given(town(), st.integers(-2000, 2000), st.integers(0, 59))
def test_prop_p9_shifting_every_timestamp_by_the_same_amount_keeps_counts(cases, days, minutes):
    """REQ-DET-1, 2, 3 (testing.md #14): a uniform time shift leaves counts and gaps unchanged."""
    delta = timedelta(days=days, minutes=minutes)
    moved = [
        replace(c, open_utc=c.open_utc + delta, close_utc=None if c.close_utc is None else c.close_utc + delta)
        for c in cases
    ]
    a, b = detect(cases), detect(moved)
    assert tier_counts(a) == tier_counts(b)
    assert [(z.zombie_id, round(z.gap_days, 9)) for z in a.zombies] == [(z.zombie_id, round(z.gap_days, 9)) for z in b.zombies]


@given(town(), st.data())
def test_prop_p10_duplicating_a_closed_case_never_increases_the_zombie_count(cases, data):
    """REQ-DET-1, 3 (testing.md #15): same place, type, open and close time, new ID."""
    # A predecessor of a linked successor is left out: duplicating it makes the duplicate a member of its own incident
    # (clarification S12/S17), and the successor then re-reports that incident instead of continuing the predecessor
    # (ZD step 9). That is a conflict between testing.md #15 and ZD step 9, reported to the owner (needs-human).
    predecessors = {pid for c in cases for pid in c.predecessor_ids}
    closed = [c for c in cases if c.is_closed and c.id not in predecessors]
    if not closed:
        return
    original = data.draw(st.sampled_from(closed))
    dup = replace(original, id="Z999")
    before, after = detect(cases), detect(cases + [dup])
    assert len(after.zombies) <= len(before.zombies), (brief(cases), original.id, [z.zombie_id for z in before.zombies],
                                                       [z.zombie_id for z in after.zombies])


@given(town(), st.randoms(use_true_random=False))
def test_prop_p4_detection_is_invariant_to_input_row_order(cases, rnd):
    """REQ-EXP-1.3 (testing.md #5): the whole detection result is the same for any input order."""
    shuffled = cases[:]
    rnd.shuffle(shuffled)
    assert detect(cases) == detect(shuffled)
