"""REQ-ING-XWALK.1-3 and REQ-ING-CATCH.1-5: crosswalk join, link table, catch-all inheritance."""

from __future__ import annotations

import duckdb

from undead311.ingest.crosswalk import apply_crosswalk, link_table

SLO = "Street Light Other"


def make_norm(rows: list[tuple[str, str, str, str | None]]) -> duckdb.DuckDBPyConnection:
    """rows: (id, system, type_raw, closure_text)."""
    con = duckdb.connect()
    con.execute("create table cases_norm(id varchar, system varchar, type_raw varchar, closure_text varchar)")
    con.executemany("insert into cases_norm values (?,?,?,?)", rows)
    return con


def fam(con, cid):
    return con.execute(
        "select type_family, scope_tier, predecessor_ids, catch_all from cases_x where id = ?", [cid]
    ).fetchone()


def test_req_ing_xwalk_1_family_tier_and_flags_come_from_type_families_csv():
    """REQ-ING-XWALK.1: family, tier, city_originated_type and catch_all by (system, type_raw)."""
    con = make_norm([
        ("L1", "legacy", "Request for Pothole Repair", None),
        ("L2", "legacy", "Pothole Repair (Internal)", None),
        ("N1", "new", "Pothole", None),
        ("N2", "new", "Traffic Signal Request", None),
    ])  # fmt: skip
    apply_crosswalk(con)
    assert fam(con, "L1")[:2] == ("pothole_roadway", "core")
    assert con.execute("select city_originated_type from cases_x where id = 'L2'").fetchone() == (True,)
    assert con.execute("select city_originated_type from cases_x where id = 'L1'").fetchone() == (False,)
    assert fam(con, "N2")[:2] == ("traffic_signal", "sensitivity")


def test_req_ing_xwalk_2_unlisted_type_has_no_family_or_tier():
    """REQ-ING-XWALK.2: a type that is not listed is out of scope (NULL tier, counted by clean)."""
    con = make_norm([("L1", "legacy", "Some Brand New Type", None)])
    apply_crosswalk(con)
    assert fam(con, "L1")[:2] == (None, None)


def test_req_ing_catch_1_link_table_reads_only_transfer_closure_texts():
    """REQ-ING-CATCH.1: only transfer texts with a BCS id produce links; boilerplate advice does not."""
    con = make_norm([
        ("L1", "legacy", "Request for Pothole Repair", "Case Closed. Resubmitted as BCS-00000010"),
        ("L2", "legacy", "Sign Repair", "Please open a new case if this persists"),
        ("L3", "legacy", "Sign Repair", "Case Closed. See new case BCS-00000011"),
        ("N9", "new", "Pothole", "Resubmitted as BCS-00000012"),
    ])  # fmt: skip
    assert link_table(con) == {
        "BCS-00000010": [("L1", "Request for Pothole Repair")],
        "BCS-00000011": [("L3", "Sign Repair")],
    }


def test_req_ing_catch_2_linked_catch_all_inherits_core_family_and_tier():
    """REQ-ING-CATCH.2, .5: a Street Light Other linked from a pothole is a pothole in the headline scope."""
    con = make_norm([
        ("L1", "legacy", "Request for Pothole Repair", "Resubmitted as BCS-00000010"),
        ("BCS-00000010", "new", SLO, None),
    ])
    report = apply_crosswalk(con)
    assert fam(con, "BCS-00000010") == ("pothole_roadway", "core", "L1", True)
    assert report.catch_all_outcomes == {"inherited_core": 1}


def test_req_ing_catch_4_catch_all_linked_only_to_excluded_types_is_excluded():
    """REQ-ING-CATCH.4: all predecessors share an excluded family -> the case inherits `excluded`."""
    con = make_norm([
        ("L1", "legacy", "Encampments", "Resubmitted as BCS-00000010"),
        ("BCS-00000010", "new", SLO, None),
    ])
    report = apply_crosswalk(con)
    assert fam(con, "BCS-00000010")[:2] == ("people_services", "excluded")
    assert report.catch_all_outcomes == {"inherited_excluded": 1}


def test_req_ing_catch_3_disagreeing_predecessors_stay_sensitivity():
    """REQ-ING-CATCH.3: predecessors from two families -> default family (streetlight), tier sensitivity."""
    con = make_norm([
        ("L1", "legacy", "Request for Pothole Repair", "Resubmitted as BCS-00000010"),
        ("L2", "legacy", "Sign Repair", "See new case BCS-00000010"),
        ("BCS-00000010", "new", SLO, None),
    ])
    report = apply_crosswalk(con)
    assert fam(con, "BCS-00000010") == ("streetlight", "sensitivity", "L1;L2", True)
    assert report.catch_all_outcomes == {"ambiguous_or_unlisted": 1}


def test_req_ing_catch_3_unlisted_predecessor_type_stays_sensitivity():
    """REQ-ING-CATCH.3: one predecessor type that is not in type_families.csv -> sensitivity."""
    con = make_norm([
        ("L1", "legacy", "A Type Nobody Listed", "Resubmitted as BCS-00000010"),
        ("BCS-00000010", "new", SLO, None),
    ])
    apply_crosswalk(con)
    assert fam(con, "BCS-00000010")[:2] == ("streetlight", "sensitivity")


def test_req_ing_catch_3_unlinked_catch_all_stays_sensitivity_with_default_family():
    """REQ-ING-CATCH.3: no link -> streetlight family for matching (clarification S18), tier sensitivity."""
    con = make_norm([("BCS-00000010", "new", SLO, None)])
    report = apply_crosswalk(con)
    assert fam(con, "BCS-00000010") == ("streetlight", "sensitivity", "", True)
    assert report.catch_all_outcomes == {"unlinked": 1}


def test_req_ing_catch_1_non_catch_all_successor_still_records_predecessors():
    """REQ-ING-CATCH.1: any new-system successor lists its linked legacy ids; its own family is unchanged."""
    con = make_norm([
        ("L1", "legacy", "Request for Pothole Repair", "Resubmitted as BCS-00000010"),
        ("BCS-00000010", "new", "Pothole", None),
    ])
    apply_crosswalk(con)
    assert fam(con, "BCS-00000010") == ("pothole_roadway", "core", "L1", False)
