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
    assert payloads["judge_tour.json"]["provisional"] is True and status["warnings"] == []
    (tmp_path / "judge_tour_override.json").write_text(json.dumps(["x", "y", "z"]))
    _, status = build_stats(result, {c.id: c for c in cs}, "v1", day(300), labels_dir=tmp_path)
    assert "ignored" in status["warnings"][0]
    few = detect([mk("A", 0, 1), mk("R", 5)])
    payloads, status = build_stats(few, {"A": mk("A", 0, 1), "R": mk("R", 5)}, "v1", day(300))
    assert "judge_tour.json" not in payloads and "fewer than 3" in status["warnings"][0]
