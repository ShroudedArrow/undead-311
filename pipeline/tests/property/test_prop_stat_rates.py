"""P5 (testing.md #10) and P1 part 2 (testing.md #3). REQ-STAT-SF.2, REQ-STAT-INT.1-2, REQ-STAT-EXP.1."""

from __future__ import annotations

import random
from dataclasses import replace

from helpers import day
from hypothesis import given
from hypothesis import strategies as st
from strategies import town

from undead311.detect.core import detect
from undead311.export.writers import validate
from undead311.stats.rates import scorecard_payload, scorecards

END = day(400)


def with_on_time(cases, seed):
    rng = random.Random(seed)
    return [replace(c, on_time=rng.choice([True, False, None])) for c in cases]


@given(town(), st.integers(0, 10_000))
def test_prop_stat_5_raw_stayed_fixed_is_at_most_on_time_in_every_group(cases, seed):
    """REQ-STAT-SF.2, testing.md #10 (P5)."""
    cases = with_on_time(cases, seed)
    result = detect(cases)
    for c in scorecards(result, {x.id: x for x in cases}, END):
        assert c.stayed_fixed_raw.k <= c.on_time.k
        assert c.stayed_fixed_raw.n == c.on_time.n == c.n_on_time_known <= c.n_closed
        if c.on_time.rate is not None:
            assert c.stayed_fixed_raw.rate <= c.on_time.rate


@given(town(), st.integers(0, 10_000))
def test_prop_stat_1_every_exported_rate_is_in_zero_one_or_null_with_a_reason(cases, seed):
    """REQ-STAT-INT.1-2, REQ-STAT-EXP.1, testing.md #3 (P1 part 2): the payload validates and bounds nest."""
    cases = with_on_time(cases, seed)
    result = detect(cases)
    payload = scorecard_payload(scorecards(result, {x.id: x for x in cases}, END), result, "v")
    validate("scorecard", payload)
    for card in payload["scorecards"]:
        for key in ("on_time", "stayed_fixed_raw"):
            r = card[key]
            if r["n"] == 0:
                assert r["rate"] is None and r["lo"] is None and r["hi"] is None and r["reason"] == "no_cases"
            else:
                assert 0 <= r["lo"] <= r["rate"] <= r["hi"] <= 1 and r["reason"] is None


@given(town(), st.integers(0, 10_000))
def test_prop_stat_1_headline_rows_are_invariant_to_input_order(cases, seed):
    """REQ-STAT-EXP.2: the same cases in another order give the same scorecards."""
    cases = with_on_time(cases, seed)
    shuffled = list(cases)
    random.Random(seed).shuffle(shuffled)
    a = scorecards(detect(cases), {x.id: x for x in cases}, END)
    b = scorecards(detect(shuffled), {x.id: x for x in shuffled}, END)
    assert a == b
