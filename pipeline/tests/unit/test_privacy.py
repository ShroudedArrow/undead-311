"""REQ-EXP-PRIV.1: block-level privacy for resident-driven repeat offenders on residential or unknown-class streets."""

from __future__ import annotations

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
    chain_resurrection_ids,
    grid_cell_center,
    load_segment_info,
    offender_location,
    resident_driven,
    street_kind,
)
from undead311.export.writers import ExportContext, build_payloads, validate
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
    assert chain_resurrection_ids(result.zombies, "A") == list("BCDEFGH")
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
