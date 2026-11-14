"""REQ-STAT-SF.1, .2, .4, REQ-STAT-INT.2, REQ-STAT-TIER.2, REQ-STAT-EXP.1: the raw scorecard, by hand."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from helpers import day, mk

from undead311.detect.core import detect
from undead311.export.writers import ContractError, validate
from undead311.stats.pipeline import build_stats, run_stats
from undead311.stats.rates import CITYWIDE, scorecard_payload, scorecards

END = day(300)


def ot(case, on_time):
    return replace(case, on_time=on_time)


def town():
    """Eligible originals 500 m apart: A on time and quiet; B on time and re-reported (headline zombie); C overdue;
    D unknown. M (made safe, on time) is re-reported by a new-system case, so its zombie is `source_unknown`."""
    return [
        ot(mk("A", 0, 1), True),
        ot(mk("B", 0, 1, x=500.0), True),
        mk("RB", 10, x=500.0),  # resident re-report of B, still open
        ot(mk("C", 0, 1, x=1000.0), False),
        ot(mk("D", 0, 1, x=1500.0), None),
        ot(mk("M", 0, 1, x=2000.0, label="made_safe_temporary"), True),
        mk("RM", 10, x=2000.0, system="new"),
    ]


def card(cards, family, tier_set):
    return next(c for c in cards if c.family == family and c.tier_set == tier_set)


def test_req_stat_sf_headline_scorecard_counts_by_hand():
    cs = town()
    result = detect(cs)
    assert result.count("headline") == 1 and result.count("source_unknown") == 1
    c = card(scorecards(result, {x.id: x for x in cs}, END), CITYWIDE, "headline")
    assert (c.n_closed, c.n_on_time_known) == (5, 4)  # D has no on_time: left out and counted
    assert (c.on_time.k, c.on_time.n) == (3, 4)  # A, B, M
    assert (c.stayed_fixed_raw.k, c.stayed_fixed_raw.n) == (
        2,
        4,
    )  # A, M; B was resurrected; RM is source_unknown
    assert c.stayed_fixed_adj is None  # needs the baseline (REQ-STAT-SF.3, credibility layer)
    assert c.on_time.rate == 0.75 and c.stayed_fixed_raw.rate == 0.5
    assert c.on_time.lo < 0.75 < c.on_time.hi  # REQ-STAT-SF.4


def test_req_stat_tier_2_all_tier_counts_the_source_unknown_zombie_but_the_headline_does_not():
    cs = town()
    cards = scorecards(detect(cs), {x.id: x for x in cs}, END)
    assert card(cards, CITYWIDE, "headline").stayed_fixed_raw.k == 2
    assert card(cards, CITYWIDE, "all").stayed_fixed_raw.k == 1  # only A


def test_req_stat_sf_family_rows_sum_to_citywide_and_are_sorted():
    cs = [ot(mk("A", 0, 1), True), ot(mk("S", 0, 1, x=500.0, family="sign"), False)]
    cards = scorecards(detect(cs), {x.id: x for x in cs}, END)
    assert [(c.family, c.tier_set) for c in cards] == sorted((c.family, c.tier_set) for c in cards)
    fam = [c for c in cards if c.tier_set == "headline" and c.family != CITYWIDE]
    assert {c.family for c in fam} == {"pothole_roadway", "sign"}
    assert sum(c.n_closed for c in fam) == card(cards, CITYWIDE, "headline").n_closed == 2


def test_req_stat_int_2_a_group_with_no_known_on_time_values_is_null_not_zero():
    cs = [mk("A", 0, 1)]
    c = card(scorecards(detect(cs), {x.id: x for x in cs}, END), CITYWIDE, "headline")
    assert c.n_closed == 1 and c.n_on_time_known == 0
    assert c.on_time.rate is None and c.on_time.reason == "no_cases"
    assert c.stayed_fixed_raw.rate is None and c.stayed_fixed_raw.reason == "no_cases"


def test_req_stat_sf_2_planned_follow_ups_and_separate_deaths_count_as_not_resurrected():
    cs = [
        ot(mk("A", 0, 1, label="made_safe_temporary"), True),
        mk("RA", 5, source="Employee Generated"),  # planned follow-up: not a zombie
        ot(mk("B", 0, 1, x=500.0, label="duplicate"), True),
        mk("RB", 5, x=500.0),  # separate death: not a zombie
    ]
    result = detect(cs)
    assert not result.zombies and result.planned_followups and result.separate_deaths
    c = card(scorecards(result, {x.id: x for x in cs}, END), CITYWIDE, "headline")
    assert (c.on_time.k, c.stayed_fixed_raw.k, c.stayed_fixed_raw.n) == (2, 2, 2)


def test_req_stat_sf_originals_not_fully_observed_are_left_out():
    cs = [ot(mk("A", 0, 1), True), ot(mk("N", 250, 251, x=500.0), True)]  # N closes 49 days before END
    c = card(scorecards(detect(cs), {x.id: x for x in cs}, END), CITYWIDE, "headline")
    assert c.n_closed == 1


def test_req_stat_exp_1_payload_validates_and_counts_the_tiers():
    cs = town()
    result = detect(cs)
    payload = scorecard_payload(scorecards(result, {x.id: x for x in cs}, END), result, "v1")
    validate("scorecard", payload)
    assert payload["counts"] == {"headline": 1, "source_unknown": 1, "city_rereport": 0, "sensitivity": 0}
    assert payload["data_version"] == "v1"


def test_req_stat_exp_1_an_out_of_range_rate_is_refused_by_the_schema():
    cs = town()
    result = detect(cs)
    payload = scorecard_payload(scorecards(result, {x.id: x for x in cs}, END), result, "v1")
    payload["scorecards"][0]["on_time"]["rate"] = 1.5
    with pytest.raises(ContractError):
        validate("scorecard", payload)


def test_req_stat_exp_1_run_stats_writes_validated_files_under_stats(tmp_path):
    cs = town()
    by_id = {x.id: x for x in cs}
    status = run_stats(None, detect(cs), by_id, tmp_path, data_version="v1", data_end=END)
    excess = json.loads((tmp_path / "stats" / "excess.json").read_text())
    placebo = excess["placebo"]  # six originals say nothing about calibration: no warning below MIN_CLUSTERS (REQ-STAT-PLACEBO.2, ops#115)
    assert placebo["calibration_warning"] is False and status["calibration_warning"] is None
    written = {p.name for p in (tmp_path / "stats").iterdir()}
    assert "scorecard.json" in written and "stats_status.json" in written
    assert json.loads((tmp_path / "stats" / "scorecard.json").read_text())["data_version"] == "v1"


def test_req_stat_exp_1_nothing_is_written_when_a_payload_is_invalid(tmp_path, monkeypatch):
    cs = town()
    result = detect(cs)
    by_id = {x.id: x for x in cs}

    def bad(*args, **kw):
        payloads, status = build_stats(*args, **kw)
        payloads["scorecard.json"]["counts"].pop("headline")
        return payloads, status

    monkeypatch.setattr("undead311.stats.pipeline.build_stats", bad)
    with pytest.raises(ContractError):
        run_stats(None, result, by_id, tmp_path, data_version="v1", data_end=END)
    assert not (tmp_path / "stats").exists()


def test_req_stat_sf_1_cases_from_table_reads_on_time_and_tolerates_a_missing_column():
    import duckdb

    from undead311.detect.cases import cases_from_table

    con = duckdb.connect()
    con.execute(
        "create table t as select * from (values ('a', 'legacy', 'core', timestamp '2024-01-01', 42.3, -71.1, true), "
        "('b', 'legacy', 'core', timestamp '2024-01-01', 42.3, -71.1, NULL::boolean)) v(id, system, scope_tier, "
        "open_time_utc, lat, lon, on_time)"
    )
    assert [c.on_time for c in cases_from_table(con, "t")] == [True, None]
    con.execute("alter table t drop column on_time")
    assert [c.on_time for c in cases_from_table(con, "t")] == [None, None]
