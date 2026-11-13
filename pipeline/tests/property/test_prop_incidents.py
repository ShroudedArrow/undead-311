"""Properties P7 (partition) and P12 (a late case is never a member): REQ-DET-1.1, REQ-DET-1.4, testing.md #12 and #18."""

from __future__ import annotations

from datetime import timedelta

from hypothesis import given
from strategies import town

from undead311.detect.core import detect


@given(town())
def test_prop_p7_incidents_partition_the_closed_in_scope_cases(cases):
    """REQ-DET-1.1: every closed in-scope case is in exactly one incident, and nothing else is."""
    result = detect(cases)
    members = [m for i in result.incidents for m in i.member_ids]
    assert len(members) == len(set(members))
    assert set(members) == {c.id for c in cases if c.is_closed}
    for i in result.incidents:
        assert i.incident_id == min(i.member_ids)


@given(town())
def test_prop_p12_a_case_opened_at_or_after_the_earliest_member_close_is_never_a_member(cases):
    """REQ-DET-1.4: members opened strictly before the incident's earliest close; the span limit holds."""
    by_id = {c.id: c for c in cases}
    for inc in detect(cases).incidents:
        ms = [by_id[m] for m in inc.member_ids]
        first_close = min(m.close_utc for m in ms)
        # every member except possibly the ones that define the earliest close opened before it
        assert all(m.open_utc < first_close for m in ms)
        if len(ms) > 1:  # a lone case may itself last longer than the span limit
            assert max(m.close_utc for m in ms) - min(m.open_utc for m in ms) <= timedelta(days=7)
