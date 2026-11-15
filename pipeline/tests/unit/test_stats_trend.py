"""REQ-STAT-TREND.1, REQ-STAT-EXP.1: rolling 6-month trends of the two-number scorecard, by hand."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from helpers import day, mk

from undead311.detect.core import detect
from undead311.export.writers import ContractError, validate
from undead311.stats.rates import CITYWIDE
from undead311.stats.trend import TREND_MONTHS, month_index, month_label, trend_payload, trend_rows

END = day(400)
# T0 is 2024-03-04. Originals close in Mar, Apr, May, Jun, Jul, Aug and Sep 2024 (days 1, 40, 70, 100, 130, 160, 190).
CLOSE_DAYS = [1, 40, 70, 100, 130, 160, 190]
ON_TIME = [True, True, False, True, True, True, False]


def town(on_time=ON_TIME, rereport_first=True):
    cs = []
    for i, (d, ot) in enumerate(zip(CLOSE_DAYS, on_time, strict=True)):
        cs.append(replace(mk(f"O{i}", d - 1, d, x=i * 500.0), on_time=ot))
    if rereport_first:
        cs.append(mk("R0", 11, x=0.0))  # a resident re-report 10 days after the March original closed: a headline zombie
    return cs


def rows_of(cs, family=CITYWIDE, tier_set="headline"):
    result = detect(cs)
    return [r for r in trend_rows(result, {c.id: c for c in cs}, END) if r["family"] == family and r["tier_set"] == tier_set]


def month_index_of(label: str) -> int:
    y, m = label.split("-")
    return int(y) * 12 + int(m) - 1


def test_req_stat_trend_1_the_window_is_six_calendar_months():
    assert TREND_MONTHS == 6
    assert month_label(month_index(day(0))) == "2024-03" and month_label(month_index(day(190))) == "2024-09"


def test_req_stat_trend_1_windows_pool_six_months_by_hand():
    """Seven closing months Mar..Sep give two full windows. Mar..Aug: 6 cases, on time Mar, Apr, Jun, Jul, Aug = 5, and the
    March original was resurrected, so stayed fixed = 4. Apr..Sep: 6 cases, on time Apr, Jun, Jul, Aug = 4, none resurrected
    in the window, stayed fixed = 4."""
    cs = town()
    assert detect(cs).count("headline") == 1
    rows = rows_of(cs)
    assert [(r["window_start"], r["window_end"]) for r in rows] == [("2024-03", "2024-08"), ("2024-04", "2024-09")]
    a, b = rows
    assert (a["n_closed"], a["n_on_time_known"], a["on_time"]["k"], a["stayed_fixed_raw"]["k"]) == (6, 6, 5, 4)
    assert (b["n_closed"], b["n_on_time_known"], b["on_time"]["k"], b["stayed_fixed_raw"]["k"]) == (6, 6, 4, 4)
    assert a["on_time"]["rate"] == pytest.approx(5 / 6) and a["stayed_fixed_raw"]["rate"] == pytest.approx(4 / 6)
    assert a["on_time"]["lo"] < 5 / 6 < a["on_time"]["hi"]  # REQ-STAT-INT


def test_req_stat_trend_1_no_single_month_is_ever_a_window():
    """Fewer than 6 months of originals give no window at all; a window never covers fewer than 6 months."""
    cs = [c for c in town() if c.id in {"O0", "O1", "O2", "O3", "O4", "R0"}]  # Mar..Jul: 5 months
    assert rows_of(cs) == []
    for r in rows_of(town()):
        assert month_index_of(r["window_end"]) - month_index_of(r["window_start"]) + 1 == TREND_MONTHS


def test_req_stat_trend_1_one_odd_month_moves_only_the_windows_that_hold_it_and_by_one_case_in_six():
    """12 closing months (Mar 2024 to Feb 2025) give 7 windows. One overdue month changes the windows that contain it and
    leaves the others alone; no window moves by more than one case in six."""
    days = [1, 40, 70, 100, 130, 160, 190, 220, 250, 280, 310, 339]  # one closing in each month, Mar 2024 to Feb 2025

    def build(odd):
        return [replace(mk(f"O{i}", d - 1, d, x=i * 500.0), on_time=not (odd and i == 5)) for i, d in enumerate(days)]

    base, odd = rows_of(build(False)), rows_of(build(True))
    assert len(base) == len(odd) == 7
    changed = [a["window_end"] for a, b in zip(base, odd, strict=True) if a["on_time"]["k"] != b["on_time"]["k"]]
    assert changed == [f"2024-{m:02d}" for m in (8, 9, 10, 11, 12)] + ["2025-01"]  # the 6 windows that hold August, not the Feb one
    for a, b in zip(base, odd, strict=True):
        assert abs(a["on_time"]["rate"] - b["on_time"]["rate"]) <= 1 / 6 + 1e-9


def test_req_stat_trend_1_unknown_on_time_is_left_out_of_both_rates_and_counted():
    cs = town([True, True, False, None, True, True, False])
    a = rows_of(cs)[0]
    assert (a["n_closed"], a["n_on_time_known"], a["on_time"]["n"], a["stayed_fixed_raw"]["n"]) == (6, 5, 5, 5)


def test_req_stat_trend_1_a_window_with_no_known_on_time_has_null_rates_with_a_reason():
    cs = town([None] * 7)
    a = rows_of(cs)[0]
    assert a["on_time"]["rate"] is None and a["on_time"]["reason"] == "no_cases" and a["stayed_fixed_raw"]["rate"] is None


def test_req_stat_trend_1_stayed_fixed_never_exceeds_on_time_in_a_window():
    for r in rows_of(town()) + rows_of(town(), tier_set="all"):
        assert r["stayed_fixed_raw"]["k"] <= r["on_time"]["k"]


def test_req_stat_tier_2_the_headline_trend_leaves_out_a_source_unknown_zombie_and_the_all_tier_counts_it():
    """A new-system re-report after a made-safe closure is `source_unknown`: not in the headline, in the all tier."""
    cs = [
        replace(mk(f"O{i}", d - 1, d, x=i * 500.0, label="made_safe_temporary" if i == 0 else "resolved"), on_time=True)
        for i, d in enumerate(CLOSE_DAYS)
    ]
    cs.append(mk("R0", 11, x=0.0, system="new"))
    result = detect(cs)
    assert result.count("headline") == 0 and result.count("source_unknown") == 1
    head = rows_of(cs)[0]["stayed_fixed_raw"]["k"]
    all_ = rows_of(cs, tier_set="all")[0]["stayed_fixed_raw"]["k"]
    assert (head, all_) == (6, 5)


def test_req_stat_trend_1_families_get_their_own_rows_and_citywide_is_their_sum():
    """Originals alternate pothole and sidewalk: in the Mar..Aug window pothole holds O0, O2, O4 and sidewalk O1, O3, O5."""
    cs = [
        replace(mk(f"O{i}", d - 1, d, x=i * 500.0, family="sidewalk" if i % 2 else "pothole_roadway"), on_time=True)
        for i, d in enumerate(CLOSE_DAYS)
    ]
    rows = trend_rows(detect(cs), {c.id: c for c in cs}, END)
    first = {r["family"]: r for r in rows if r["tier_set"] == "headline" and r["window_end"] == "2024-08"}
    assert first[CITYWIDE]["n_closed"] == 6
    assert (first["pothole_roadway"]["n_closed"], first["sidewalk"]["n_closed"]) == (3, 3)


def test_req_stat_trend_1_the_payload_validates_is_sorted_and_says_the_windows_overlap():
    cs = town()
    payload = trend_payload(detect(cs), {c.id: c for c in cs}, END, "v1")
    validate("trends", payload)
    assert payload["window_months"] == 6 and "share 5 months" in payload["note"] and payload["seed"] is None
    keys = [(r["family"], r["tier_set"], r["window_end"]) for r in payload["rows"]]
    assert keys == sorted(keys)


def test_req_stat_trend_1_the_schema_rejects_a_one_month_window():
    cs = town()
    payload = trend_payload(detect(cs), {c.id: c for c in cs}, END, "v1")
    bad = json.loads(json.dumps(payload))
    bad["window_months"] = 1
    with pytest.raises(ContractError):
        validate("trends", bad)


def test_req_stat_trend_1_a_window_shorter_than_two_months_is_refused():
    cs = town()
    with pytest.raises(ValueError):
        trend_rows(detect(cs), {c.id: c for c in cs}, END, months=1)


def test_req_stat_exp_2_trends_are_deterministic_and_ignore_input_order():
    cs = town()
    a = trend_payload(detect(cs), {c.id: c for c in cs}, END, "v1")
    b = trend_payload(detect(list(reversed(cs))), {c.id: c for c in reversed(cs)}, END, "v1")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
