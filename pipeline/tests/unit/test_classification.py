"""REQ-DET-PF.1-4, REQ-DET-TIER.1-4, REQ-DET-SEP.1: planned follow-ups, tiers, separate deaths."""

from __future__ import annotations

from helpers import mk

from undead311.detect.core import detect


def run(label="resolved", r_system="legacy", r_source="Constituent Call", r_city_type=False, **orig):
    cs = [mk("A", 0, 1, label=label, **orig), mk("R", 10, system=r_system, source=r_source, city_type=r_city_type)]
    return detect(cs)


def test_req_det_pf_1_city_originated_legacy_re_report_after_made_safe_is_a_planned_follow_up():
    """REQ-DET-PF.1: Employee Generated after made_safe_temporary is not a zombie."""
    r = run("made_safe_temporary", r_source="Employee Generated")
    assert r.zombies == [] and [(p.incident_id, p.resurrection_id) for p in r.planned_followups] == [("A", "R")]


def test_req_det_pf_1_city_originated_type_counts_even_with_a_resident_source():
    """REQ-DET-PF.1: an (Internal) work-order type is city-originated."""
    assert run("referred", r_city_type=True).planned_followups


def test_req_det_pf_2_resident_re_report_after_made_safe_is_tagged_after_temporary_fix():
    """REQ-DET-PF.2: counted, tagged, headline tier."""
    z = run("made_safe_temporary").zombies[0]
    assert z.after_temporary_fix and not z.source_unknown and z.tier == "headline"


def test_req_det_pf_3_new_system_re_report_after_made_safe_is_source_unknown():
    """REQ-DET-PF.3: tagged source_unknown, tier source_unknown, never after_temporary_fix (clarification S13)."""
    z = run("made_safe_temporary", r_system="new").zombies[0]
    assert z.source_unknown and not z.after_temporary_fix and z.tier == "source_unknown"


def test_req_det_pf_4_other_labels_are_not_affected_even_for_city_sources():
    """REQ-DET-PF.4, REQ-DET-TIER.3: after `resolved` a city-originated re-report is still a possible zombie, in the
    `city_rereport` tier outside the headline (ZD step 6, ops#29); it is not a planned follow-up."""
    r = run("resolved", r_source="Employee Generated")
    z = r.zombies[0]
    assert z.tier == "city_rereport" and z.city_rereport and not z.after_temporary_fix and not z.source_unknown
    assert not r.planned_followups and r.headline_count == 0


def test_req_det_tier_3_sensitivity_wins_over_the_city_tier():
    """REQ-DET-TIER.1, .3: a sensitivity-scope original keeps its zombie in the sensitivity tier even for a city re-report;
    the `city_rereport` flag still says the re-report is a city case."""
    r = detect([mk("A", 0, 1, tier="sensitivity"), mk("R", 10, source="Employee Generated")])
    z = r.zombies[0]
    assert z.tier == "sensitivity" and z.city_rereport


def test_req_det_pf_classification_uses_the_resurrection_not_later_reports():
    """REQ-DET-PF (intro): only the earliest attached R is classified; later ones count in reports_after."""
    cs = [mk("A", 0, 1, label="made_safe_temporary"), mk("R1", 5, source="Employee Generated"),
          mk("R2", 6, source="Constituent Call")]  # fmt: skip
    r = detect(cs)
    assert [p.resurrection_id for p in r.planned_followups] == ["R1"] and r.zombies == []


def test_req_det_sep_1_invalid_and_duplicate_closures_are_separate_deaths():
    """REQ-DET-SEP.1: reported separately, not as zombies."""
    for label in ("invalid", "duplicate"):
        r = run(label)
        assert r.zombies == [] and [(s.label, s.rereport_id) for s in r.separate_deaths] == [(label, "R")]


def test_req_det_tier_1_sensitivity_wins_over_source_unknown_and_headline():
    """REQ-DET-TIER.1: a sensitivity original or re-report makes the zombie sensitivity-tier."""
    assert run("resolved", tier="sensitivity").zombies[0].tier == "sensitivity"
    cs = [mk("A", 0, 1), mk("R", 10, tier="sensitivity")]
    assert detect(cs).zombies[0].tier == "sensitivity"
    z = run("made_safe_temporary", r_system="new", tier="sensitivity").zombies[0]
    assert z.tier == "sensitivity" and z.source_unknown  # nothing is lost: the flag is kept


def test_req_det_tier_2_headline_count_counts_only_headline_zombies():
    """REQ-DET-TIER.2-3: per-tier counts; zombies of every tier are exported."""
    cs = [mk("A", 0, 1), mk("R", 5), mk("B", 0, 1, x=500, label="made_safe_temporary"), mk("S", 5, x=500, system="new"),
          mk("C", 0, 1, x=900, tier="sensitivity"), mk("T", 5, x=900)]  # fmt: skip
    r = detect(cs)
    assert (r.count("headline"), r.count("source_unknown"), r.count("sensitivity")) == (1, 1, 1)
    assert r.headline_count == 1 and len(r.zombies) == 3
