"""REQ-EXP-PRIV.1: block-level privacy for resident-driven repeat offenders on residential or unknown-class streets."""

from __future__ import annotations

import itertools
import json
from dataclasses import replace

import pytest
from helpers import at, examples, mk
from hypothesis import given, settings
from hypothesis import strategies as st

from undead311.detect.core import detect
from undead311.export.privacy import (
    GRID_CELL_M,
    SegmentInfo,
    block_level_locations,
    chain_rereport_ids,
    grid_cell_center,
    load_segment_info,
    offender_location,
    resident_driven,
    segment_midpoint,
    street_kind,
)
from undead311.export.writers import ExportContext, build_payloads, case_record, validate
from undead311.ingest.snap import M_PER_DEG_LAT, M_PER_DEG_LON

MID = (42.3001, -71.1001)
SEGS = {
    "S_RES": SegmentInfo(MID, "Local"),
    "S_UNK": SegmentInfo(MID, None),
    "S_ART": SegmentInfo(MID, "Principal Arterial"),
}
POINT = (42.30123, -71.10234)


def town(*, segment="S_RES", city_first=0, n=4):
    """A repeat offender: n-1 closures, each re-reported. The first `city_first` re-reports are city-originated (they are
    possible zombies in the city_rereport tier and keep the chain going); the rest are residents' (headline)."""
    cs = [mk(chr(65 + i), 5 * i, 5 * i + 1, segment=segment) for i in range(n - 1)]
    cs.append(mk(chr(65 + n - 1), 5 * (n - 1), segment=segment))
    return [replace(c, source="Employee Generated") if 1 <= i <= city_first else c for i, c in enumerate(cs)]


def payload(cases, segments=SEGS):
    result = detect(cases)
    ctx = ExportContext(data_version="v", run_time="t", segment_info=segments)
    out = build_payloads(result, {c.id: c for c in cases}, ctx)["repeat_offenders.json"]
    validate("repeat_offenders", out)
    return out["repeat_offenders"], result


# --- offender_location: one test per branch -------------------------------------------------------------------


def test_req_exp_priv_1_resident_driven_residential_segment_gives_the_segment_midpoint():
    assert offender_location(POINT, "S_RES", True, SEGS) == (*MID, True)


def test_req_exp_priv_1_unknown_class_segment_is_block_level_too():
    assert offender_location(POINT, "S_UNK", True, SEGS) == (*MID, True)


def test_req_exp_priv_1_known_non_residential_street_keeps_the_exact_point():
    assert offender_location(POINT, "S_ART", True, SEGS) == (*POINT, False)


def test_req_exp_priv_1_city_driven_chain_keeps_the_exact_point():
    assert offender_location(POINT, "S_RES", False, SEGS) == (*POINT, False)


def test_req_exp_priv_1_unsnapped_resident_chain_gets_the_100_m_cell_center():
    lat, lon, block = offender_location(POINT, None, True, SEGS)
    assert block and (lat, lon) == grid_cell_center(*POINT) and (lat, lon) != POINT


def test_req_exp_priv_1_snapped_but_no_geometry_falls_back_to_the_cell_center():
    """No SAM file (or an ID missing from it): the class is unknown, so the safe side is block level."""
    assert offender_location(POINT, "S_RES", True, None) == (*grid_cell_center(*POINT), True)
    assert offender_location(POINT, "S_GONE", True, SEGS) == (*grid_cell_center(*POINT), True)


# --- classification and cells -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "kind"),
    [(None, "unknown"), ("", "unknown"), ("  ", "unknown"), ("Local", "residential"), ("Residential", "residential"),
     ("Minor Arterial", "non_residential"), ("HIGHWAY", "non_residential"), ("Collector", "non_residential"),
     ("something else", "residential")],
)  # fmt: skip
def test_req_exp_priv_1_street_kind(raw, kind):
    assert street_kind(raw) == kind


def test_req_exp_priv_1_grid_cell_center_is_within_half_a_cell_and_stable_inside_the_cell():
    lat, lon = grid_cell_center(*POINT)
    dx = (lon - POINT[1]) * M_PER_DEG_LON
    dy = (lat - POINT[0]) * M_PER_DEG_LAT
    assert abs(dx) <= GRID_CELL_M / 2 + 0.1 and abs(dy) <= GRID_CELL_M / 2 + 0.1
    assert grid_cell_center(lat, lon) == (lat, lon)


@given(st.floats(42.2, 42.45), st.floats(-71.2, -70.9))
@settings(max_examples=examples(60), deadline=None)
def test_prop_req_exp_priv_1_cell_center_is_close_and_idempotent(lat, lon):
    c_lat, c_lon = grid_cell_center(lat, lon)
    assert abs(c_lat - lat) * M_PER_DEG_LAT <= GRID_CELL_M / 2 + 0.2
    assert abs(c_lon - lon) * M_PER_DEG_LON <= GRID_CELL_M / 2 + 0.2
    assert grid_cell_center(c_lat, c_lon) == (c_lat, c_lon)


# --- resident-driven rule ---------------------------------------------------------------------------------------


def test_req_exp_priv_1_more_than_half_must_be_resident_reports():
    cases = {
        "r1": mk("r1", 0), "r2": mk("r2", 0),
        "c1": mk("c1", 0, source="Employee Generated"), "c2": mk("c2", 0, city_type=True),
        "n1": mk("n1", 0, system="new", source=None),
    }  # fmt: skip
    assert resident_driven(["r1", "r2", "c1"], cases)
    assert not resident_driven(["r1", "c1"], cases)  # exactly half is not "more than half"
    assert not resident_driven(["c1", "c2", "r1"], cases)
    assert not resident_driven(["n1", "c1"], cases)  # half again
    assert resident_driven(
        ["n1", "n1", "c1"], cases
    )  # a new-system re-report has no origin field: counts as resident
    assert not resident_driven([], cases)


# --- through the export --------------------------------------------------------------------------------------------


def test_req_exp_priv_1_export_moves_a_resident_driven_residential_chain_to_the_midpoint():
    cases = town(segment="S_RES")
    (o,), result = payload(cases)
    assert [c.chain_id for c in result.repeat_offenders] == ["A"]
    assert o["block_level"] is True and (o["lat"], o["lon"]) == MID
    # no exported coordinate equals a case point of the chain
    assert all((o["lat"], o["lon"]) != (round(c.lat, 6), round(c.lon, 6)) for c in cases)


def test_req_exp_priv_1_export_keeps_the_point_of_a_city_driven_chain():
    cases = town(
        segment="S_RES", city_first=4, n=8
    )  # 4 of the 7 re-reports are the city's; 3 headline zombies remain
    (o,), result = payload(cases)
    assert chain_rereport_ids(result.attribution, next(c for c in result.chains).incident_ids) == list("BCDEFGH")
    assert [c.headline_count for c in result.chains] == [3]
    assert o["block_level"] is False
    assert (o["lat"], o["lon"]) == (round(cases[0].lat, 6), round(cases[0].lon, 6))


def test_req_exp_priv_1_export_keeps_the_point_on_an_arterial():
    (o,), _ = payload(town(segment="S_ART"))
    assert o["block_level"] is False


def test_req_exp_priv_1_export_uses_the_cell_center_for_an_unsnapped_chain():
    cases = town(segment=None)
    (o,), _ = payload(cases, segments=None)
    assert o["block_level"] is True
    assert (o["lat"], o["lon"]) == grid_cell_center(round(cases[0].lat, 6), round(cases[0].lon, 6))


def test_req_exp_priv_1_block_level_output_is_deterministic():
    assert payload(town())[0] == payload(list(reversed(town())))[0]


# --- loading the SAM file -----------------------------------------------------------------------------------------


def test_req_exp_priv_1_load_segment_info_reads_midpoint_and_class(tmp_path):
    f = tmp_path / "sam.geojson"
    line = [list(at(0, 0))[::-1], list(at(100, 0))[::-1]]  # GeoJSON order is (lon, lat)
    feats = [
        {"type": "Feature", "properties": {"SEGMENT_ID": 7, "st_class": "Local"},
         "geometry": {"type": "LineString", "coordinates": line}},
        {"type": "Feature", "properties": {"SEGMENT_ID": 8},
         "geometry": {"type": "LineString", "coordinates": line}},
        {"type": "Feature", "properties": {"SEGMENT_ID": 9}, "geometry": {"type": "Point", "coordinates": line[0]}},
    ]  # fmt: skip
    f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    info = load_segment_info(f)
    assert sorted(info) == ["7", "8"]  # a non-line feature is skipped
    assert info["7"].street_class == "Local" and info["8"].street_class is None
    lat, lon = at(50, 0)
    assert info["7"].midpoint == (round(lat, 6), round(lon, 6))
    assert load_segment_info(tmp_path / "missing.geojson") == {}


# --- every attached re-report counts (ops#168) -------------------------------------------------------------------


def test_req_exp_priv_1_every_attached_rereport_counts_not_only_the_first():
    """One incident, three re-reports: the first is the city's, two are residents'. Resurrections alone say 0 of 1
    resident; every attached re-report says 2 of 3 (ZD step 5: `reports_after` counts them all)."""
    cases = [
        mk("A", 0, 1), mk("B", 3, 4, source="Employee Generated"), mk("C", 8, 9), mk("D", 12, 13),
        mk("E", 16, 17), mk("F", 20, 21), mk("G", 24),
    ]  # fmt: skip
    cases = [replace(c, source="Employee Generated") if c.id in ("B", "D", "F") else c for c in cases]
    result = detect(cases)
    index = {c.id: c for c in cases}
    chain = result.chains[0]
    ids = chain_rereport_ids(result.attribution, chain.incident_ids)
    assert ids == ["B", "C", "D", "E", "F", "G"]
    assert resident_driven(ids, index) is False  # 3 of 6 is not more than half
    only_first = sorted(z.resurrection_id for z in result.zombies if z.chain_id == chain.chain_id)
    assert only_first == ids  # a chain's re-reports are one per incident here


def test_req_exp_priv_1_extra_rereports_on_one_incident_can_flip_the_verdict():
    """Original A (closed day 1). B is the city's; C, D and E are residents' and attach to A too: reports_after = 4."""
    cases = [mk("A", 0, 1), replace(mk("B", 3), source="Employee Generated"), mk("C", 4), mk("D", 5), mk("E", 6)]
    result = detect(cases)
    assert [z.reports_after for z in result.zombies] == [4]
    ids = chain_rereport_ids(result.attribution, [result.zombies[0].incident_id])
    assert ids == ["B", "C", "D", "E"]
    index = {c.id: c for c in cases}
    assert resident_driven(ids, index) is True  # 3 of 4
    assert resident_driven([result.zombies[0].resurrection_id], index) is False  # the old test: B alone, 0 of 1


def test_req_exp_priv_1_unattached_cases_are_not_rereports_of_the_chain():
    assert chain_rereport_ids({"X": "i1", "Y": "i2", "Z": "i1"}, ["i1"]) == ["X", "Z"]
    assert chain_rereport_ids({}, ["i1"]) == []


# --- block level reaches every exported row of the chain (ops#167) ---------------------------------------------------


def exports(cases, segments=SEGS):
    result = detect(cases)
    ctx = ExportContext(data_version="v", run_time="t", segment_info=segments)
    out = build_payloads(result, {c.id: c for c in cases}, ctx)
    for name in ("points", "repeat_offenders"):
        validate(name, out[f"{name}.json"])
    return out, result


def test_req_exp_priv_1_points_and_cards_of_a_block_level_chain_carry_no_case_point():
    cases = town(segment="S_RES")
    out, _ = exports(cases)
    exact = {(round(c.lat, 6), round(c.lon, 6)) for c in cases}
    pts = out["points.json"]
    assert pts["n"] == 3 and {(a, b) for a, b in zip(pts["lat"], pts["lon"], strict=True)} == {MID}
    cards = [c for k, v in out.items() if k.startswith("cards/") for c in v["cards"]]
    assert len(cards) == 3
    for card in cards:
        for side in ("original", "rereport"):
            assert (card[side]["lat"], card[side]["lon"]) == MID
            assert card[side]["street"] is None
            assert (card[side]["lat"], card[side]["lon"]) not in exact


def test_req_exp_priv_1_rows_of_a_city_driven_chain_keep_the_exact_point_and_street():
    cases = [replace(c, street="1 Elm St") for c in town(segment="S_RES", city_first=4, n=8)]
    out, _ = exports(cases)
    assert out["repeat_offenders.json"]["repeat_offenders"][0]["block_level"] is False
    cards = [c for k, v in out.items() if k.startswith("cards/") for c in v["cards"]]
    assert cards and all(c["original"]["street"] == "1 Elm St" for c in cards)
    assert (out["points.json"]["lat"][0], out["points.json"]["lon"][0]) != MID


def test_req_exp_priv_1_a_zombie_outside_any_repeat_offender_chain_keeps_its_point():
    cases = [replace(mk("A", 0, 1), street="9 Oak St"), mk("B", 3)]
    out, result = exports(cases)
    assert result.repeat_offenders == []
    card = next(c for k, v in out.items() if k.startswith("cards/") for c in v["cards"])
    assert card["original"]["street"] == "9 Oak St"
    assert (out["points.json"]["lat"][0], out["points.json"]["lon"][0]) == (round(cases[0].lat, 6), round(cases[0].lon, 6))


def test_req_exp_priv_1_case_record_block_drops_the_street_and_uses_the_block_point():
    c = replace(mk("A", 0, 1), street="1 Elm St")
    assert case_record(c)["street"] == "1 Elm St"
    r = case_record(c, (42.1, -71.2))
    assert (r["street"], r["lat"], r["lon"]) == (None, 42.1, -71.2)


def test_req_exp_priv_1_block_level_locations_match_the_repeat_offenders_file():
    cases = town(segment="S_RES")
    out, result = exports(cases)
    locs = block_level_locations(result, {c.id: c for c in cases}, SEGS)
    (o,) = out["repeat_offenders.json"]["repeat_offenders"]
    assert locs[o["chain_id"]] == (o["lat"], o["lon"], o["block_level"])


# --- segment midpoint in metres (ops#169) -----------------------------------------------------------------------------


def lonlat(x_m, y_m):
    """GeoJSON (lon, lat) of a point x_m east and y_m north of the projection origin."""
    return [x_m / M_PER_DEG_LON, y_m / M_PER_DEG_LAT]


def metres(mid):
    return mid[1] * M_PER_DEG_LON, mid[0] * M_PER_DEG_LAT


def test_req_exp_priv_1_midpoint_of_a_bent_line_is_half_the_length_not_half_the_degrees():
    """100 m north then 100 m east: the half-way point is the corner (100 m along). In degree space it would be 13 m off."""
    x0, y0 = 5000.0, 7000.0
    mid = segment_midpoint([[lonlat(x0, y0), lonlat(x0, y0 + 100), lonlat(x0 + 100, y0 + 100)]])
    mx, my = metres(mid)
    assert abs(mx - x0) < 0.2 and abs(my - (y0 + 100)) < 0.2


def test_req_exp_priv_1_midpoint_of_a_multilinestring_is_on_a_part_with_no_connector():
    """A 300 m part and a 100 m part, 5 km apart: half of the 400 m total is 200 m along the first part, on the street.
    A connector between them would put the midpoint kilometres from both parts."""
    a0, b0 = (0.0, 0.0), (5000.0, 0.0)
    parts = [[lonlat(*a0), lonlat(a0[0] + 300, 0)], [lonlat(*b0), lonlat(b0[0] + 100, 0)]]
    mx, my = metres(segment_midpoint(parts))
    assert abs(my) < 0.2 and abs(mx - 200) < 0.2
    # a longer second part: the midpoint falls inside it, 50 m past its start
    parts2 = [[lonlat(*a0), lonlat(100, 0)], [lonlat(*b0), lonlat(b0[0] + 300, 0)]]  # total 400, half 200 = 100 into part 2
    mx2, _ = metres(segment_midpoint(parts2))
    assert abs(mx2 - (b0[0] + 100)) < 0.2


def test_req_exp_priv_1_midpoint_of_a_degenerate_line_is_none():
    assert segment_midpoint([]) is None
    assert segment_midpoint([[lonlat(1, 1)]]) is None
    assert segment_midpoint([[lonlat(1, 1), lonlat(1, 1)]]) is None


@given(st.lists(st.tuples(st.floats(0, 800), st.floats(0, 800)), min_size=2, max_size=6))
@settings(max_examples=examples(60), deadline=None)
def test_prop_req_exp_priv_1_midpoint_lies_on_the_line_at_half_its_length(pts):
    mid = segment_midpoint([[lonlat(x, y) for x, y in pts]])
    pieces = list(itertools.pairwise(pts))
    lens = [((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in pieces]
    if sum(lens) < 1e-3:
        return
    assert mid is not None
    left = sum(lens) / 2
    for (a, b), n in zip(pieces, lens, strict=True):  # the point half the length along, found independently
        if n > 0 and left <= n:
            want = (a[0] + left / n * (b[0] - a[0]), a[1] + left / n * (b[1] - a[1]))
            break
        left -= n
    else:
        want = pts[-1]
    mx, my = metres(mid)
    assert abs(mx - want[0]) < 0.2 and abs(my - want[1]) < 0.2


def test_req_exp_priv_1_load_segment_info_reads_a_multilinestring(tmp_path):
    f = tmp_path / "sam.geojson"
    parts = [[lonlat(0, 0), lonlat(300, 0)], [lonlat(5000, 0), lonlat(5100, 0)]]
    feat = {"type": "Feature", "properties": {"SEGMENT_ID": 1}, "geometry": {"type": "MultiLineString", "coordinates": parts}}
    f.write_text(json.dumps({"type": "FeatureCollection", "features": [feat]}))
    mx, my = metres(load_segment_info(f)["1"].midpoint)
    assert abs(mx - 200) < 0.2 and abs(my) < 0.2
