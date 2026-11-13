"""REQ-STAT-INT: Wilson and bootstrap intervals against hand-computed values."""

from __future__ import annotations

import math

import pytest

from undead311.stats.intervals import NO_CASES, bootstrap, make_rate, wilson


def test_req_stat_int_1_wilson_matches_a_hand_computed_value():
    """k=8, n=10: centre = (0.8 + 1.96^2/20) / (1 + 1.96^2/10) and the textbook interval is (0.490, 0.943)."""
    lo, hi = wilson(8, 10)  # type: ignore[misc]
    assert lo == pytest.approx(0.4902, abs=1e-3) and hi == pytest.approx(0.9433, abs=1e-3)


def test_req_stat_int_1_wilson_at_the_edges_stays_inside_zero_and_one():
    lo0, hi0 = wilson(0, 20)  # type: ignore[misc]
    lo1, hi1 = wilson(20, 20)  # type: ignore[misc]
    assert lo0 == 0.0 and 0 < hi0 < 0.2
    assert hi1 == 1.0 and 0.8 < lo1 < 1


def test_req_stat_int_2_zero_denominator_is_null_with_a_reason_never_zero():
    assert wilson(0, 0) is None
    r = make_rate(0, 0)
    assert (r.rate, r.lo, r.hi, r.n, r.reason) == (None, None, None, 0, NO_CASES)
    assert r.to_json()["rate"] is None


def test_req_stat_int_1_a_known_rate_has_no_reason():
    r = make_rate(3, 4)
    assert r.rate == 0.75 and r.reason is None and r.lo < 0.75 < r.hi


def test_req_stat_int_1_wilson_rejects_k_above_n():
    with pytest.raises(ValueError):
        wilson(5, 4)


def test_req_stat_int_1_bootstrap_is_seeded_and_brackets_the_mean():
    values = [0.0, 1.0] * 20
    a = bootstrap(values, lambda x: float(x.mean()), seed=311)
    assert a == bootstrap(values, lambda x: float(x.mean()), seed=311)
    spread = [i * 0.37 % 1 for i in range(40)]
    assert bootstrap(spread, lambda x: float(x.mean()), seed=311) != bootstrap(
        spread, lambda x: float(x.mean()), seed=312
    )
    assert a[0] < 0.5 < a[1] and 0 <= a[0] and a[1] <= 1  # type: ignore[index]
    # the 95% half-width of a mean of 40 fair coin flips is about 1.96 * 0.5 / sqrt(40)
    assert (a[1] - a[0]) / 2 == pytest.approx(1.96 * 0.5 / math.sqrt(40), abs=0.04)  # type: ignore[index]


def test_req_stat_int_2_bootstrap_of_nothing_is_null():
    assert bootstrap([], lambda x: float(x.mean()), seed=1) is None
