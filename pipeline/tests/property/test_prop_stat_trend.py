"""Properties of the rolling trends (REQ-STAT-TREND.1; testing.md #3, #5, #10)."""

from __future__ import annotations

import random
from dataclasses import replace

from helpers import day
from hypothesis import given
from hypothesis import strategies as st
from strategies import town

from undead311.detect.core import detect
from undead311.export.writers import validate
from undead311.stats.trend import TREND_MONTHS, trend_payload

END = day(400)


def with_on_time(cases, seed):
    rng = random.Random(seed)
    return [replace(c, on_time=rng.choice([True, False, None])) for c in cases]


def label_index(label: str) -> int:
    y, m = label.split("-")
    return int(y) * 12 + int(m) - 1


@given(town(), st.integers(0, 10_000))
def test_prop_stat_trend_every_window_spans_six_months_and_every_rate_is_valid(cases, seed):
    """REQ-STAT-TREND.1, testing.md #3 and #10: windows are 6 months, rates in [0, 1] or null with a reason, stayed fixed
    never above on time, and the payload validates."""
    cases = with_on_time(cases, seed)
    payload = trend_payload(detect(cases), {c.id: c for c in cases}, END, "v")
    validate("trends", payload)
    for r in payload["rows"]:
        assert label_index(r["window_end"]) - label_index(r["window_start"]) + 1 == TREND_MONTHS
        assert r["stayed_fixed_raw"]["k"] <= r["on_time"]["k"] and r["on_time"]["n"] == r["n_on_time_known"] <= r["n_closed"]
        for key in ("on_time", "stayed_fixed_raw"):
            x = r[key]
            if x["n"] == 0:
                assert x["rate"] is None and x["reason"] == "no_cases"
            else:
                assert 0 <= x["lo"] <= x["rate"] <= x["hi"] <= 1


@given(town(), st.integers(0, 10_000))
def test_prop_stat_trend_results_do_not_depend_on_input_order(cases, seed):
    """REQ-STAT-TREND.1, testing.md #5."""
    cases = with_on_time(cases, seed)
    shuffled = list(cases)
    random.Random(seed).shuffle(shuffled)
    a = trend_payload(detect(cases), {c.id: c for c in cases}, END, "v")
    b = trend_payload(detect(shuffled), {c.id: c for c in shuffled}, END, "v")
    assert a == b
