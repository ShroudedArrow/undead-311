"""Burstiness flag and the excess with and without flagged spots (REQ-STAT-BASE.2; methods.md "Acceptance and limits"; ops#141).

A spot with at least 8 reports is flagged when the index of dispersion of its monthly report counts is above 2, or when its
reports fall in fewer than half as many distinct months as a random spread of them gives, M (1 - (1 - 1/M)^K) for K reports over
M observed months (ops#146 (b), ops#170 item 10). A spot with fewer than 8 reports is never flagged. Each excess row also
reports the excess without the flagged spots."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest
from helpers import day, mk
from hypothesis import given
from hypothesis import strategies as st
from test_stats_hybrid import END, town

from undead311.detect.core import detect
from undead311.export.writers import validate
from undead311.stats.baseline import (
    BURST_ACTIVE_RATIO,
    BURST_DISPERSION,
    BURST_MIN_REPORTS,
    BaselineModel,
    burstiness,
    excess_rows,
    expected_distinct_months,
)
from undead311.stats.pipeline import run_stats


def ts(y: int, m: int, d: int) -> float:
    return datetime(y, m, d, tzinfo=UTC).timestamp()


def test_req_stat_base_2_the_flag_thresholds_are_the_owner_values():
    """methods.md and ops#170 item 10: at least 8 reports, dispersion above 2, or fewer than half the expected distinct months."""
    assert BURST_DISPERSION == 2.0 and BURST_ACTIVE_RATIO == 0.5 and BURST_MIN_REPORTS == 8


def test_req_stat_base_2_the_expected_distinct_months_follow_the_owner_formula_by_hand():
    """M (1 - (1 - 1/M)^K): M = 12, K = 8 gives 12 (1 - (11/12)^8) = 12 (1 - 0.49850) = 6.018; K = 1 gives exactly 1; M = 1 gives 1."""
    assert expected_distinct_months(12, 8) == pytest.approx(12 * (1 - (11 / 12) ** 8)) == pytest.approx(6.018, abs=1e-3)
    assert expected_distinct_months(12, 1) == pytest.approx(1.0)
    assert expected_distinct_months(1, 5) == pytest.approx(1.0)
    assert expected_distinct_months(0, 5) == 0.0 and expected_distinct_months(5, 0) == 0.0


def test_req_stat_base_2_one_report_in_each_of_twelve_months_is_not_flagged_by_either_test():
    """Hand count: counts 1 x 12, months 12, active 12, variance 0 so dispersion 0; K = 12 >= 8 so the spot is assessed."""
    opens = np.array([ts(2024, m, 10) for m in range(1, 13)])
    b = burstiness(opens, ts(2024, 12, 20))
    assert (b.months, b.active, b.dispersion, b.assessed) == (12, 12, 0.0, True) and not b.flagged


def test_req_stat_base_2_a_month_with_most_of_the_reports_has_a_dispersion_above_two():
    """Hand count over 12 months: 12 reports in Jan and one in each other month. counts = [12, 1 x 11], mean 23/12,
    sample variance (sum (c - mean)^2) / 11 = 9.73..., dispersion 9.73 / 1.917 = 5.08."""
    opens = np.array([ts(2024, 1, d) for d in range(1, 13)] + [ts(2024, m, 15) for m in range(2, 13)])
    b = burstiness(opens, ts(2024, 12, 31))
    counts = np.array([12] + [1] * 11)
    assert b.dispersion == pytest.approx(counts.var(ddof=1) / counts.mean())
    assert b.dispersion > 5.0 and b.by_dispersion and not b.by_concentration and b.flagged


def test_req_stat_base_2_reports_in_fewer_than_half_the_expected_distinct_months_are_flagged():
    """Hand count over 12 observed months with 8 reports: expected distinct months 6.018, half is 3.009. Reports in 3 months
    (3 < 3.009) are flagged by concentration; in 4 months (4 >= 3.009) they are not, and dispersion there is 0.97 / 0.667 = 1.45 (counts
    2, 2, 2, 2, 0 x 8: mean 2/3, sum of squares 10.67, variance 0.97)."""
    end = ts(2024, 12, 31)
    three = burstiness(np.array([ts(2024, 1, 5), ts(2024, 1, 6), ts(2024, 1, 7), ts(2024, 2, 5), ts(2024, 2, 6), ts(2024, 2, 7),
                                 ts(2024, 3, 5), ts(2024, 3, 6)]), end)  # fmt: skip
    four = burstiness(np.array([ts(2024, m, d) for m in (1, 2, 3, 4) for d in (5, 6)]), end)
    assert (three.months, three.active, three.reports, three.by_concentration) == (12, 3, 8, True)
    assert (four.months, four.active, four.reports, four.by_concentration) == (12, 4, 8, False)
    assert four.dispersion == pytest.approx(1.4545, abs=0.001) and not four.by_dispersion and not four.flagged
    assert three.expected_active == pytest.approx(6.018, abs=1e-3)


def test_req_stat_base_2_a_spot_with_fewer_than_eight_reports_is_never_flagged():
    """ops#146 (b): 6 reports in January and one in December (7 reports, 12 months) have a dispersion of 5.1 and would be
    flagged, but they are not assessed. A seventh January report makes 8 reports (dispersion 6.1): assessed and flagged."""
    end = ts(2024, 12, 31)
    jan = [ts(2024, 1, d) for d in range(1, 8)]
    eight = burstiness(np.array(jan + [ts(2024, 12, 20)]), end)
    seven = burstiness(np.array(jan[:6] + [ts(2024, 12, 20)]), end)
    assert (seven.reports, seven.assessed, seven.by_dispersion, seven.by_concentration, seven.flagged) == (7, False, False, False, False)
    assert seven.dispersion == pytest.approx(5.1, abs=0.1)  # it would have been flagged without the minimum
    assert (eight.reports, eight.assessed, eight.flagged) == (8, True, True) and eight.dispersion == pytest.approx(6.1, abs=0.1)


def test_req_stat_base_2_a_spot_with_two_reports_in_the_first_months_of_a_long_watch_is_not_flagged_any_more():
    """The old rule flagged this spot (2 of 46 months); with 2 reports it is now never flagged."""
    b = burstiness(np.array([ts(2020, 1, 5), ts(2020, 2, 5)]), ts(2023, 10, 31))
    assert b.months == 46 and b.active == 2 and not b.assessed and not b.flagged


def test_req_stat_base_2_the_observed_months_run_from_the_first_report_to_the_data_end():
    """A spot first reported in October and watched to December has 3 observed months, whatever happened before."""
    b = burstiness(np.array([ts(2024, 10, 3), ts(2024, 11, 3)]), ts(2024, 12, 5))
    assert (b.months, b.active) == (3, 2) and not b.by_concentration


def test_req_stat_base_2_a_spot_observed_for_one_month_has_no_dispersion_and_is_not_flagged():
    b = burstiness(np.array([ts(2024, 5, 3), ts(2024, 5, 9)]), ts(2024, 5, 20))
    assert b.dispersion is None and not b.flagged


def test_req_stat_base_2_a_spot_with_no_reports_is_not_flagged():
    assert not burstiness(np.empty(0), ts(2024, 5, 20)).flagged


@given(
    st.lists(st.integers(min_value=0, max_value=1400), min_size=1, max_size=40),
    st.integers(min_value=0, max_value=10_000),
)
def test_req_stat_base_2_the_flag_ignores_row_order_and_counts_are_consistent(days, seed):
    """Property: the flag is a function of the set of report times (order-invariant); active <= months; dispersion >= 0."""
    opens = np.array([day(d).timestamp() for d in days])
    shuffled = opens.copy()
    np.random.default_rng(seed).shuffle(shuffled)
    a, b = burstiness(np.sort(opens), day(1400).timestamp()), burstiness(shuffled, day(1400).timestamp())
    assert a == b
    assert 1 <= a.active <= a.months
    assert a.dispersion is None or a.dispersion >= 0.0


def bursty_town(seed, spots=120, closed_after=2.0):
    """Each gap 10 or 200 days at random (a null town: nothing resurrects by cause)."""
    rng = np.random.default_rng(seed)
    out = []
    for s in range(spots):
        t, n = 0.0, 0
        while True:
            t += float(rng.choice([10.0, 200.0]))
            if t > END:
                break
            out.append(mk(f"S{s:03d}-{n:03d}", t, t + closed_after, x=s * 1000.0, segment=f"seg{s}"))
            n += 1
    return out


def family_row(cs, boot=200):
    res = detect(cs)
    m = BaselineModel({c.id: c for c in cs}, res, data_end=day(END))
    rows = excess_rows(m, 311, boot)
    return m, rows, next(r for r in rows if r.kind == "family" and r.tier_set == "headline")


def test_req_stat_base_2_every_excess_row_reports_the_excess_without_the_flagged_spots():
    """On a bursty null town most spots are flagged; the row keeps its own numbers and adds the unflagged ones. The
    flagged originals plus the unflagged ones are the row's originals, and the unflagged excess is smaller (the bias of
    a bursty town sits in the flagged spots: +483 against +78 at 300 spots, seed 5, measured for docs/METHODS.md)."""
    _m, rows, row = family_row(bursty_town(5))
    assert row.n_bursty > 0 and row.unflagged is not None
    assert row.n_bursty + row.unflagged.n_originals == row.n_originals
    assert row.unflagged.observed <= row.observed and row.unflagged.expected <= row.expected
    assert row.unflagged.excess == pytest.approx(row.unflagged.observed - row.unflagged.expected)
    assert row.unflagged.excess < row.excess
    assert row.unflagged.lo <= row.unflagged.excess <= row.unflagged.hi
    for r in rows:
        assert r.n_bursty + (r.unflagged.n_originals if r.unflagged else 0) == r.n_originals


def test_req_stat_base_2_a_town_with_no_flagged_spot_has_the_same_excess_with_and_without():
    """A report every 30 days at every spot (seed 5): no spot is flagged, so the unflagged row is the full row."""
    _m, _rows, row = family_row(town((30.0,), 5, spots=60))
    assert row.n_bursty == 0 and row.unflagged is not None
    assert (row.unflagged.observed, row.unflagged.n_originals) == (row.observed, row.n_originals)
    assert row.unflagged.excess == pytest.approx(row.excess)


def test_req_stat_base_2_a_row_whose_originals_are_all_flagged_has_no_unflagged_part():
    """A spot reported 8 times in its first 21 days of ~46 months (expected distinct months 7.0, half is 3.5, active at most 2): flagged
    by concentration, so nothing is left."""
    cs = [mk(f"A{i}", 3 * i, 3 * i + 1, segment="s") for i in range(8)]
    _m, _rows, row = family_row(cs, boot=50)
    assert row.n_bursty == row.n_originals > 0 and row.unflagged is None


def test_req_stat_base_2_the_seeded_rows_do_not_depend_on_the_input_order():
    """Reproducible for a fixed seed and invariant to the row order of the input (testing.md #5, #7)."""
    cs = bursty_town(6, spots=60)
    _m, rows_a, _ = family_row(cs)
    _m, rows_b, _ = family_row(list(reversed(cs)))
    assert [r.to_json() for r in rows_a] == [r.to_json() for r in rows_b]


@pytest.mark.parametrize("flag", [False, True])
def test_req_stat_base_2_the_full_rows_are_identical_whatever_the_flag_says(flag, monkeypatch):
    """ops#153: the full rows' observed, expected, excess and interval are the same with `is_bursty` patched to always False
    and to always True, and the same as the real flag. A regression that shares one generator between the full and the
    unflagged draws would move the full interval and fail here."""
    cs = bursty_town(6, spots=60)
    _m, _rows, real = family_row(cs)
    monkeypatch.setattr(BaselineModel, "is_bursty", lambda self, incident: flag)
    _m, _rows, patched = family_row(cs)
    for field in ("observed", "expected", "excess", "lo", "hi", "n_originals"):
        assert getattr(patched, field) == getattr(real, field), field
    assert (patched.unflagged is None) == flag
    assert patched.n_bursty == (patched.n_originals if flag else 0)


def test_req_stat_base_2_the_flag_never_reads_closures():
    """Closing every report later changes no flag: it depends only on report times and the span (so the placebo shift
    cannot change it)."""
    flags = []
    for closed_after in (2.0, 9.0):
        cs = bursty_town(7, spots=30, closed_after=closed_after)
        m = BaselineModel({c.id: c for c in cs}, detect(cs), data_end=day(END))
        flags.append({k: m.burst(k) for k in m.groups})
    assert flags[0] == flags[1] and any(b.flagged for b in flags[0].values())


def test_req_stat_exp_1_excess_json_carries_burstiness_and_validates(tmp_path):
    """The export has the burstiness summary and the per-row `without_bursty`, and validates against excess.schema.json."""
    cs = town((60.0,), 5, spots=30, span=700)
    by_id = {c.id: c for c in cs}
    run_stats(None, detect(cs), by_id, tmp_path, data_version="v1", data_end=day(700))
    payload = json.loads((tmp_path / "stats" / "excess.json").read_text())
    validate("excess", payload)
    b = payload["burstiness"]
    assert b["flagged_spots"] <= b["spots"] and b["flagged_originals"] <= b["originals"]
    assert b["flagged_by_dispersion"] <= b["flagged_spots"] <= b["flagged_by_dispersion"] + b["flagged_by_concentration"]
    for row in payload["rows"]:
        assert "n_bursty" in row and "without_bursty" in row


def test_req_stat_base_2_the_burstiness_summary_covers_the_cohort_of_the_excess_rows(tmp_path):
    """ops#152: `flagged_originals` and `originals` of the summary equal the sums of `n_bursty` and `n_originals` over the
    headline family rows. An original closed within WINDOW_DAYS of the data end is not in the cohort of either."""
    cs = bursty_town(5, spots=40)
    cs.append(mk("LATE", END - 10, END - 9, x=999_000.0, segment="late"))  # closed 9 days before the end: not fully observed
    by_id = {c.id: c for c in cs}
    run_stats(None, detect(cs), by_id, tmp_path, data_version="v1", data_end=day(END))
    payload = json.loads((tmp_path / "stats" / "excess.json").read_text())
    fam = [r for r in payload["rows"] if r["kind"] == "family" and r["tier_set"] == "headline"]
    b = payload["burstiness"]
    assert b["originals"] == sum(r["n_originals"] for r in fam) > 0
    assert b["flagged_originals"] == sum(r["n_bursty"] for r in fam) > 0


def test_req_stat_exp_1_the_schema_accepts_an_old_file_without_the_burst_fields_and_rejects_a_bad_one():
    from undead311.export.writers import ContractError

    row = {"kind": "family", "name": "f", "tier_set": "headline", "observed": 1, "expected": 0.5, "excess": 0.5, "lo": 0.0, "hi": 1.0}
    validate("excess", {"data_version": "v", "rows": [row]})
    bad = {**row, "without_bursty": {"observed": 1}}
    with pytest.raises(ContractError):
        validate("excess", {"data_version": "v", "rows": [bad]})


def test_req_stat_base_2_the_bursty_null_town_row_is_pinned_to_docs_methods():
    """The measured limit in docs/METHODS.md (300 spots, seed 5, 300 replicates): the full row is +483 and above 0, the row
    without the 10 spots flagged by the ops#146 (b) rule is +449 and still above 0, so the flag lowers the bias only a little."""
    m, _rows, row = family_row(bursty_town(5, spots=300), boot=300)
    assert round(row.excess) == 483 and row.lo > 0
    assert row.unflagged is not None and round(row.unflagged.excess) == 449 and row.unflagged.lo > 0
    assert (row.n_originals, row.unflagged.n_originals) == (3863, 3690)
    b = m.burst_summary(m.excess_cohort("headline"))
    assert (b["spots"], b["flagged_spots"], b["flagged_by_dispersion"], b["flagged_by_concentration"]) == (300, 10, 10, 0)


def test_req_stat_base_2_a_sparse_null_town_flags_under_ten_percent_of_its_spots():
    """ops#170 item 10 (owner acceptance): the sparse null town (a report every 300 days, seeds 5 and 6) flags under 10% of
    its spots. Measured for docs/METHODS.md: 0 of 296 and 0 of 297 (the first rule flagged 291 of 297)."""
    for seed in (5, 6):
        m, _rows, _row = family_row(town((300.0,), seed), boot=50)
        b = m.burst_summary(m.excess_cohort("headline"))
        assert b["spots"] > 250 and b["flagged_spots"] < 0.1 * b["spots"], (seed, b)
        assert b["assessed_spots"] <= b["spots"]


def test_req_stat_base_2_methods_documents_the_flag_its_thresholds_and_the_with_and_without_columns():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "docs" / "METHODS.md").read_text()
    for needle in ("Burstiness flag", "BURST_DISPERSION", "BURST_ACTIVE_RATIO", "BURST_MIN_REPORTS", "without_bursty",
                   "fewer than 8 reports", "M (1 - (1 - 1/M)^K)", "+483 [+438, +525]", "+449 [+405, +491] (3,690 originals)",
                   "0 of 296 and 0 of 297 spots"):
        assert needle in text, needle


def test_req_stat_base_2_methods_says_the_flag_reads_the_rereports_and_gives_the_causal_and_sample_figures():
    """ops#150, ops#151, ops#146: METHODS.md states that the flag counts the re-reports (so it reads the outcome), has the
    causal-town rows and the sample figures of the new rule, and says what stays open (live reports only)."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "docs" / "METHODS.md").read_text()
    for needle in ("the re-reports that make the zombies included", "not independent of the outcome",
                   "| Causal, report every 300 days, q = 0.4 (real resurrections) | 5 | 5 of 296 (157) (5 / 1) | +715 [+617, +792] | +692 [+607, +781] (2,270 originals) |",
                   "141 of 6,508 spots", "1,181 of the 11,590 originals", "pothole +269 [+206, +332] against +288 [+242, +338] (3,672 of 4,577)",
                   "computed from live reports only"):
        assert needle in text, needle


def test_req_stat_base_2_the_docstring_of_the_flag_names_the_rereports():
    """ops#150: the code says what METHODS.md says."""
    assert "re-reports that make the" in (burstiness.__doc__ or "")
