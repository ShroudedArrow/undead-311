"""REQ-STAT-TOUR.1: the provisional judge-mode tour."""

from __future__ import annotations

import json

from helpers import day, mk

from undead311.detect.core import detect
from undead311.export.writers import validate
from undead311.stats.pipeline import build_stats
from undead311.stats.tour import build_tour, read_override


def town_with_reports():
    """Four headline zombies at spots 500 m apart. Re-report counts: Z1 = 3, Z2 = 2, Z3 = 2, Z4 = 1."""
    cs = []
    for n, (name, reports) in enumerate([("Z1", 3), ("Z2", 2), ("Z3", 2), ("Z4", 1)]):
        x = 500.0 * n
        cs.append(mk(f"{name}-O", 0, 1, x=x))
        cs += [mk(f"{name}-R{k}", 5 + k, x=x) for k in range(reports)]
    return cs


def test_req_stat_tour_1_picks_the_three_zombies_with_most_reports_ties_by_id():
    result = detect(town_with_reports())
    tour = build_tour(result.zombies)
    assert tour.provisional is True and tour.source == "most_reports"
    assert tour.zombie_ids == (
        "Z1-O:Z1-R0",
        "Z2-O:Z2-R0",
        "Z3-O:Z3-R0",
    )  # Z4 has one report; Z2/Z3 tie, ID order


def test_req_stat_tour_1_override_wins_when_it_names_three_headline_zombies():
    result = detect(town_with_reports())
    ids = ["Z4-O:Z4-R0", "Z1-O:Z1-R0", "Z2-O:Z2-R0"]
    tour = build_tour(result.zombies, ids)
    assert tour.source == "override" and tour.zombie_ids == tuple(ids) and tour.provisional is True


def test_req_stat_tour_1_a_bad_override_is_ignored():
    result = detect(town_with_reports())
    for bad in (
        ["Z4-O:Z4-R0"],
        ["Z1-O:Z1-R0", "Z1-O:Z1-R0", "Z2-O:Z2-R0"],
        ["Z1-O:Z1-R0", "nope", "Z2-O:Z2-R0"],
    ):
        assert build_tour(result.zombies, bad).source == "most_reports"


def test_req_stat_tour_1_only_headline_zombies_are_listed():
    cs = town_with_reports() + [
        mk("M-O", 0, 1, x=5000.0, label="made_safe_temporary"),
        mk("M-R0", 5, x=5000.0, system="new"),
        mk("M-R1", 6, x=5000.0, system="new"),
        mk("M-R2", 7, x=5000.0, system="new"),
        mk("M-R3", 8, x=5000.0, system="new"),
    ]
    result = detect(cs)
    assert result.count("source_unknown") == 1
    assert all(i.startswith("Z") for i in build_tour(result.zombies).zombie_ids)


def test_req_stat_tour_1_fewer_than_three_headline_zombies_gives_no_tour():
    result = detect([mk("A", 0, 1), mk("R", 5)])
    assert build_tour(result.zombies) is None


def test_req_stat_tour_1_read_override_accepts_a_list_or_an_object_and_rejects_junk(tmp_path):
    f = tmp_path / "judge_tour_override.json"
    assert read_override(f) is None
    f.write_text(json.dumps(["a", "b", "c"]))
    assert read_override(f) == ["a", "b", "c"]
    f.write_text(json.dumps({"zombie_ids": ["a", "b", "c"]}))
    assert read_override(f) == ["a", "b", "c"]
    for junk in ("not json", json.dumps({"zombie_ids": "a"}), json.dumps([1, 2, 3])):
        f.write_text(junk)
        assert read_override(f) is None


def test_req_stat_tour_1_exported_tour_validates_and_a_missing_tour_is_a_warning(tmp_path):
    cs = town_with_reports()
    result = detect(cs)
    payloads, status = build_stats(result, {c.id: c for c in cs}, "v1", day(300), labels_dir=tmp_path)
    validate("judge_tour", payloads["judge_tour.json"])
    assert payloads["judge_tour.json"]["provisional"] is True
    assert not any("judge_tour" in w or "override" in w for w in status["warnings"])
    (tmp_path / "judge_tour_override.json").write_text(json.dumps(["x", "y", "z"]))
    _, status = build_stats(result, {c.id: c for c in cs}, "v1", day(300), labels_dir=tmp_path)
    assert any("ignored" in w for w in status["warnings"])
    few = detect([mk("A", 0, 1), mk("R", 5)])
    payloads, status = build_stats(few, {"A": mk("A", 0, 1), "R": mk("R", 5)}, "v1", day(300))
    assert "judge_tour.json" not in payloads and any("fewer than 3" in w for w in status["warnings"])


def test_req_stat_tour_1_an_explained_away_zombie_is_never_featured():
    """REQ-STAT-TOUR.1, REQ-SKEP: the Skeptic's explained_away verdict removes a zombie from the ranking and the override."""
    from dataclasses import replace

    zs = [replace(z, skeptic_verdict="explained_away") if z.zombie_id == "Z1-O:Z1-R0" else z for z in detect(town_with_reports()).zombies]
    tour = build_tour(zs)
    assert "Z1-O:Z1-R0" not in tour.zombie_ids and tour.zombie_ids == ("Z2-O:Z2-R0", "Z3-O:Z3-R0", "Z4-O:Z4-R0")
    assert build_tour(zs, ["Z1-O:Z1-R0", "Z2-O:Z2-R0", "Z3-O:Z3-R0"]).source == "most_reports"
    survivors = [replace(z, skeptic_verdict="weakened") for z in zs]
    assert "Z1-O:Z1-R0" in build_tour(survivors).zombie_ids


def test_req_stat_exp_1_tour_carries_params_and_a_null_seed():
    """REQ-STAT-EXP.1: every stats file has data_version, params and seed (null when nothing is resampled)."""
    cs = town_with_reports()
    payloads, _ = build_stats(detect(cs), {c.id: c for c in cs}, "v1", day(300))
    for name in ("judge_tour.json", "scorecard.json"):
        assert payloads[name]["seed"] is None
        assert {"WINDOW_DAYS", "RADIUS_M", "matching"} <= set(payloads[name]["params"])
        validate(name.removesuffix(".json"), payloads[name])


def test_req_stat_tour_1_provisional_ranking_skips_rereports_within_an_hour_of_the_closure():
    """REQ-STAT-TOUR.1, ops#44: a crew's work log (re-report seconds after the closure) is not on the provisional tour."""
    cs = town_with_reports()
    # a fifth spot with the most re-reports of all, the first one 10 minutes after the closure (gap < 1 h)
    cs += [mk("Q-O", 0, 1, x=3000.0), mk("Q-R0", 1, x=3000.0, open_hours=0.1)]  # 6 minutes after the closure
    cs += [mk(f"Q-R{k}", 5 + k, x=3000.0) for k in range(1, 6)]
    result = detect(cs)
    q = next(z for z in result.zombies if z.incident_id == "Q-O")
    assert q.tier == "headline" and q.gap_days * 24 < 1.0 and q.reports_after >= 5
    tour = build_tour(result.zombies)
    assert q.zombie_id not in tour.zombie_ids and tour.zombie_ids == ("Z1-O:Z1-R0", "Z2-O:Z2-R0", "Z3-O:Z3-R0")


def test_req_stat_tour_1_provisional_ranking_needs_three_zombies_past_the_gap():
    """REQ-STAT-TOUR.1, ops#44: with fewer than three resident re-reports of at least an hour, there is no provisional tour."""
    cs = []
    for n in range(3):
        cs += [mk(f"S{n}-O", 0, 1, x=500.0 * n), mk(f"S{n}-R", 1, x=500.0 * n, open_hours=0.2)]
    assert build_tour(detect(cs).zombies) is None


def test_req_stat_tour_1_survives_first_weakened_only_to_fill():
    """REQ-STAT-TOUR.1 (owner decision ops#215): "survives" zombies come first, even with fewer re-reports;
    "weakened" ones fill only when fewer than three survive; "explained_away" is never featured."""
    from dataclasses import replace

    zs = detect(town_with_reports()).zombies
    verdicts = {"Z1-O:Z1-R0": "weakened", "Z2-O:Z2-R0": "survives", "Z3-O:Z3-R0": "explained_away", "Z4-O:Z4-R0": "survives"}
    zs = [replace(z, skeptic_verdict=verdicts.get(z.zombie_id, z.skeptic_verdict)) for z in zs]
    tour = build_tour(zs)
    # Z4 has the fewest re-reports but survives, so it ranks before the weakened Z1, which only fills the third place.
    assert tour.zombie_ids == ("Z2-O:Z2-R0", "Z4-O:Z4-R0", "Z1-O:Z1-R0")
    three_survive = [replace(z, skeptic_verdict="survives") if z.zombie_id == "Z1-O:Z1-R0" else z for z in zs]
    three_survive = [replace(z, skeptic_verdict="weakened") if z.zombie_id == "Z3-O:Z3-R0" else z for z in three_survive]
    assert build_tour(three_survive).zombie_ids == ("Z1-O:Z1-R0", "Z2-O:Z2-R0", "Z4-O:Z4-R0")  # weakened Z3 left out
