"""REQ-DET-CHAIN.1-3: chains, times_risen, repeat offenders."""

from __future__ import annotations

from helpers import mk

from undead311.detect.core import detect


def chain_town(n_closed: int, **last):
    """A closes, B re-reports and closes, ... the last case stays open."""
    cs = [mk(chr(65 + i), 5 * i, 5 * i + 1) for i in range(n_closed)]
    cs.append(mk(chr(65 + n_closed), 5 * n_closed, **last))
    return cs


def test_req_det_chain_1_a_closed_resurrection_continues_the_chain():
    """REQ-DET-CHAIN.1-2: three zombies in a row share chain_id (the first incident) and times_risen = 3."""
    r = detect(chain_town(3))
    assert [(z.incident_id, z.chain_id, z.times_risen) for z in r.zombies] == [
        ("A", "A", 3), ("B", "A", 3), ("C", "A", 3),
    ]  # fmt: skip
    assert [(c.chain_id, c.times_risen, c.headline_count) for c in r.chains] == [("A", 3, 3)]


def test_req_det_chain_3_repeat_offender_needs_three_headline_zombies():
    """REQ-DET-CHAIN.3: 2 zombies is not a repeat offender; 3 is."""
    assert detect(chain_town(2)).repeat_offenders == []
    assert [c.chain_id for c in detect(chain_town(3)).repeat_offenders] == ["A"]


def test_req_det_chain_2_times_risen_counts_every_tier_but_repeat_offender_counts_headline_only():
    """REQ-DET-CHAIN.2-3: a sensitivity link counts in times_risen, not in the headline count."""
    cs = [mk("A", 0, 1), mk("B", 5, 6), mk("C", 10, 11, tier="sensitivity"), mk("D", 15)]
    r = detect(cs)
    tiers = {z.incident_id: z.tier for z in r.zombies}
    assert tiers == {"A": "headline", "B": "sensitivity", "C": "sensitivity"}
    (chain,) = r.chains
    assert (chain.times_risen, chain.headline_count) == (3, 1) and not chain.repeat_offender
    assert {z.times_risen for z in r.zombies} == {3}


def test_req_det_chain_1_a_planned_follow_up_ends_the_chain_and_starts_a_new_one():
    """REQ-DET-CHAIN.1: A -> B is a planned follow-up; B's own re-reports form a new chain starting at B."""
    cs = [mk("A", 0, 1, label="made_safe_temporary"), mk("B", 5, 6, source="Employee Generated"),
          mk("C", 10, 11), mk("D", 15)]  # fmt: skip
    r = detect(cs)
    assert [(p.incident_id, p.resurrection_id) for p in r.planned_followups] == [("A", "B")]
    assert [(z.incident_id, z.chain_id, z.times_risen) for z in r.zombies] == [("B", "B", 2), ("C", "B", 2)]


def test_req_det_chain_1_a_separate_death_ends_the_chain():
    """REQ-DET-CHAIN.1 / REQ-DET-SEP: an invalid closure is not a link."""
    cs = [mk("A", 0, 1, label="invalid"), mk("B", 5, 6), mk("C", 10)]
    r = detect(cs)
    assert [s.incident_id for s in r.separate_deaths] == ["A"]
    assert [(z.incident_id, z.chain_id, z.times_risen) for z in r.zombies] == [("B", "B", 1)]


def test_req_det_chain_2_every_record_in_a_chain_carries_the_same_total():
    """REQ-DET-CHAIN.2: two chains in one town keep separate totals."""
    cs = chain_town(2) + [mk("X", 0, 1, x=500), mk("Y", 5, x=500)]
    r = detect(cs)
    assert {z.incident_id: (z.chain_id, z.times_risen) for z in r.zombies} == {
        "A": ("A", 2), "B": ("A", 2), "X": ("X", 1),
    }  # fmt: skip
