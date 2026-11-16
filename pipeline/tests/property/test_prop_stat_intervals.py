"""P1 (part 1), testing.md #3: every interval is within [0, 1] and contains its estimate. REQ-STAT-INT.1-2."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from undead311.stats.intervals import bootstrap, make_rate, wilson

counts = st.integers(min_value=0, max_value=5000).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n)))


@given(counts)
def test_prop_stat_1_wilson_is_within_zero_one_and_contains_the_estimate(kn):
    """REQ-STAT-INT.1 (P1)."""
    k, n = kn
    r = make_rate(k, n)
    if n == 0:
        assert r.rate is None and r.lo is None and r.hi is None and r.reason == "no_cases"
        return
    assert 0.0 <= r.lo <= r.rate <= r.hi <= 1.0
    assert (r.lo, r.hi) == wilson(k, n)


@given(counts, st.floats(min_value=1.0, max_value=3.5))
def test_prop_stat_1_wider_z_never_narrows_the_interval(kn, z):
    """REQ-STAT-INT.1: a larger z gives an interval that contains the 95% one."""
    k, n = kn
    if n == 0:
        return
    lo95, hi95 = wilson(k, n, 1.96)
    lo, hi = wilson(k, n, max(z, 1.96))
    assert lo <= lo95 + 1e-12 and hi >= hi95 - 1e-12


@given(st.lists(st.floats(min_value=0, max_value=1), min_size=1, max_size=30), st.integers(0, 2**31))
def test_prop_stat_1_bootstrap_interval_is_ordered_and_within_the_data_range(values, seed):
    """REQ-STAT-INT.1: the bootstrap mean interval lies inside [min, max] of the sample and lo <= hi."""
    lo, hi = bootstrap(values, lambda x: float(x.mean()), seed, B=50)  # type: ignore[misc]
    assert lo <= hi
    assert min(values) - 1e-9 <= lo and hi <= max(values) + 1e-9
