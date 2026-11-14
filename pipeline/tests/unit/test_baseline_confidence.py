"""REQ-CONF.1-2, REQ-SKEP.1, REQ-STAT-BASE.4: baseline_p and Skeptic verdicts complete the confidence score."""

from __future__ import annotations

import json

import pytest
from helpers import mk
from hypothesis import given
from hypothesis import strategies as st
from test_pipeline import raw_folder

import undead311.pipeline as pl
import undead311.stats.pipeline as stats_pipeline
from undead311.detect.baseline import BadBaseline, apply_baselines
from undead311.detect.confidence import rescore
from undead311.detect.core import detect
from undead311.detect.skeptic import build_input
from undead311.pipeline import run_pipeline


def two_zombies():
    cs = [mk("A1", 0, 1), mk("A2", 5, None), mk("B1", 0, 1, x=300), mk("B2", 4, None, x=300)]
    return detect(cs).zombies, {c.id: c for c in cs}


def test_req_conf_2_without_baselines_nothing_changes_and_scores_stay_partial():
    zs, _ = two_zombies()
    assert apply_baselines(zs, None) == zs and apply_baselines(zs, {}) == zs
    assert all(z.baseline_p is None and z.confidence_partial for z in zs)


def test_req_conf_1_a_baseline_lowers_confidence_as_coincidence_gets_likelier():
    zs, _ = two_zombies()
    low = {z.zombie_id: z for z in apply_baselines(zs, {z.zombie_id: 0.05 for z in zs})}
    high = {z.zombie_id: z for z in apply_baselines(zs, {z.zombie_id: 0.80 for z in zs})}
    for z in zs:
        assert low[z.zombie_id].baseline_p == 0.05 and low[z.zombie_id].confidence > z.confidence > high[z.zombie_id].confidence
        assert abs((low[z.zombie_id].confidence - high[z.zombie_id].confidence) - 0.30 * (0.80 - 0.05)) < 1e-9


def test_req_conf_2_partial_turns_false_only_with_both_a_baseline_and_a_skeptic_review():
    zs, _ = two_zombies()
    only_baseline = apply_baselines(zs, {z.zombie_id: 0.1 for z in zs})
    assert all(z.confidence_partial for z in only_baseline)
    reviewed = [rescore(z, skeptic_verdict="survives", skeptic_notes="n") for z in only_baseline]
    assert not any(z.confidence_partial for z in reviewed)
    weakened = [rescore(z, skeptic_verdict="weakened", skeptic_notes="n") for z in only_baseline]
    assert not any(z.confidence_partial for z in weakened)  # weakened scores 0.5 but is a real verdict
    only_skeptic = [rescore(z, skeptic_verdict="survives", skeptic_notes="n") for z in zs]
    assert all(z.confidence_partial for z in only_skeptic)


def test_req_conf_2_a_zombie_missing_from_the_baselines_keeps_the_neutral_term():
    zs, _ = two_zombies()
    out = apply_baselines(zs, {zs[0].zombie_id: 0.2})
    assert out[0].baseline_p == 0.2 and out[1].baseline_p is None and out[1] == zs[1]


@pytest.mark.parametrize("bad", [-0.01, 1.01, float("nan"), float("inf"), "0.2", True, None])
def test_req_stat_base_4_a_baseline_outside_zero_one_is_refused(bad):
    zs, _ = two_zombies()
    with pytest.raises(BadBaseline):
        apply_baselines(zs, {zs[0].zombie_id: bad})


@given(st.floats(0, 1), st.sampled_from(["survives", "weakened", "explained_away", "not_reviewed"]))
def test_req_conf_1_confidence_stays_in_unit_interval_for_any_baseline_and_verdict(p, verdict):
    zs, _ = two_zombies()
    for z in apply_baselines(zs, {z.zombie_id: p for z in zs}):
        z = rescore(z, skeptic_verdict=verdict)
        assert 0.0 <= z.confidence <= 1.0 and z.baseline_p == p


@given(st.floats(0, 1), st.floats(0, 1))
def test_req_conf_1_confidence_never_rises_with_baseline_p(a, b):
    zs, _ = two_zombies()
    lo, hi = sorted((a, b))
    first = apply_baselines(zs[:1], {zs[0].zombie_id: lo})[0]
    second = apply_baselines(zs[:1], {zs[0].zombie_id: hi})[0]
    assert first.confidence >= second.confidence - 1e-12


def test_req_skep_1_skeptic_input_carries_baseline_p_and_selection_ignores_it():
    zs, cases = two_zombies()
    with_p = apply_baselines(zs, {zs[0].zombie_id: 0.9, zs[1].zombie_id: 0.1})
    items = build_input(with_p, cases, "v")["items"]
    assert {i["zombie_id"]: i["baseline_p"] for i in items} == {zs[0].zombie_id: 0.9, zs[1].zombie_id: 0.1}
    assert [i["zombie_id"] for i in items] == [i["zombie_id"] for i in build_input(zs, cases, "v")["items"]]


def test_req_conf_2_the_pipeline_uses_the_stats_stage_baselines_and_the_skeptic_join(tmp_path, monkeypatch):
    seen = {}

    def hook(con, result, cases, params):
        seen["ids"] = [z.zombie_id for z in result.zombies]
        return {z.zombie_id: 0.25 for z in result.zombies}

    monkeypatch.setattr(stats_pipeline, "zombie_baselines", hook, raising=False)
    monkeypatch.setattr(
        pl, "join_objections", lambda zs, path, p: [rescore(z, p, skeptic_verdict="survives", skeptic_notes="checked") for z in zs]
    )
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "d", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    [z] = json.loads((out / "zombies.json").read_text())["zombies"]
    assert seen["ids"] == [z["zombie_id"]] and z["baseline_p"] == 0.25 and z["confidence_partial"] is False
    card = next(c for f in (out / "cards").glob("*.json") for c in json.loads(f.read_text())["cards"])
    assert card["confidence_partial"] is False and card["skeptic_verdict"] == "survives"
    assert rep.baseline_zombies == 1 and rep.confidence_partial == 0
    skeptic = json.loads((tmp_path / "d" / "processed" / "skeptic_input.json").read_text())
    assert skeptic["items"][0]["baseline_p"] == 0.25


def test_req_conf_2_without_a_baseline_hook_the_pipeline_scores_stay_partial(tmp_path):
    raw, snap = raw_folder(tmp_path)
    out = tmp_path / "out"
    rep = run_pipeline(out_dir=out, raw_dir=raw, work_dir=tmp_path / "d", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    [z] = json.loads((out / "zombies.json").read_text())["zombies"]
    assert z["baseline_p"] is None and z["confidence_partial"] is True
    assert rep.baseline_zombies == 0 and rep.confidence_partial == 1


def test_req_conf_2_a_partial_baseline_is_an_anomaly_and_a_bad_one_fails_the_run(tmp_path, monkeypatch):
    raw, snap = raw_folder(tmp_path)
    monkeypatch.setattr(stats_pipeline, "zombie_baselines", lambda con, result, cases, params: {}, raising=False)
    rep = run_pipeline(out_dir=tmp_path / "o1", raw_dir=raw, work_dir=tmp_path / "d1", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert rep.baseline_zombies == 0  # an empty mapping means "not available", so no anomaly line
    monkeypatch.setattr(stats_pipeline, "zombie_baselines", lambda con, result, cases, params: {"other:id": 0.5}, raising=False)
    rep = run_pipeline(out_dir=tmp_path / "o2", raw_dir=raw, work_dir=tmp_path / "d2", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert any("baseline_p is missing for 1 of 1 zombies" in w for w in rep.warnings)
    monkeypatch.setattr(stats_pipeline, "zombie_baselines", lambda con, result, cases, params: {"1001:1002": 2.0}, raising=False)
    with pytest.raises(BadBaseline):
        run_pipeline(out_dir=tmp_path / "o3", raw_dir=raw, work_dir=tmp_path / "d3", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    assert not (tmp_path / "o3").exists()  # nothing exported


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,  # only the missing baseline counts as the expected failure; a crash in the hook is a real failure (ops#95)
    reason="blocked on durability-stats task 5: stats.pipeline has no zombie_baselines yet (ops#82). When it lands this test "
    "XPASSES and strict mode fails the suite: remove the marker and tick zombie-engine task 27.",
)
def test_req_conf_2_integration_the_real_stats_stage_gives_every_zombie_a_baseline_p(tmp_path):
    """REQ-CONF.1-2, REQ-STAT-BASE.4: no monkeypatch. A run with the real stats stage scores a zombie with baseline_p."""
    raw, snap = raw_folder(tmp_path)
    rep = run_pipeline(out_dir=tmp_path / "out", raw_dir=raw, work_dir=tmp_path / "d", snapshot_md=snap, run_time="2026-11-13T00:00:00Z")
    [z] = json.loads((tmp_path / "out" / "zombies.json").read_text())["zombies"]
    assert z["baseline_p"] is not None and rep.baseline_zombies == 1
