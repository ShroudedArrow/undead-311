"""REQ-EXP-PRIV.1 (ops#185): a zombie that is not linked to a block-level chain but sits at the same spot as one is shown at
the block too, so the map never shows a dot on a home beside the block-level chain of that home."""

from __future__ import annotations

from dataclasses import replace

from helpers import mk
from test_privacy import MID, exports, town

from undead311.detect.core import detect
from undead311.export.privacy import (
    COLOCATED_M,
    SegmentInfo,
    block_level_locations,
    block_location_by_case,
    colocated_block_locations,
)


def chain_plus(pair_x=5.0, pair_segment="S_RES"):
    """The resident-driven chain A..D (all at x = 0 on segment S_RES, days 0-16) plus an unlinked pair P, Q at `pair_x` metres
    east on `pair_segment`, opened 300 days later: Q re-reports P only, and P's address is a real one."""
    cases = town(segment="S_RES", n=4)
    cases.append(replace(mk("P", 300, 301, x=pair_x, segment=pair_segment), street="30-32 Saint Germain St"))
    cases.append(replace(mk("Q", 304, x=pair_x, segment=pair_segment), street="30-32 Saint Germain St"))
    return cases


def card_of(out, zid):
    return next(c for k, v in out.items() if k.startswith("cards/") for c in v["cards"] if c["zombie_id"] == zid)


def test_req_exp_priv_1_a_zombie_5_m_from_a_block_level_case_on_the_same_segment_is_shown_at_the_block():
    cases = chain_plus()
    out, result = exports(cases)
    assert any(o["block_level"] for o in out["repeat_offenders.json"]["repeat_offenders"])
    zid = next(z.zombie_id for z in result.zombies if z.resurrection_id == "Q")
    assert result.attribution["Q"] == "P" or zid.endswith(":Q")  # linked to its own original, not to the chain
    card = card_of(out, zid)
    for side in ("original", "rereport"):
        assert (card[side]["lat"], card[side]["lon"]) == MID and card[side]["street"] is None
    i = out["points.json"]["id"].index(zid)
    assert (out["points.json"]["lat"][i], out["points.json"]["lon"][i]) == MID


def test_req_exp_priv_1_a_zombie_beyond_the_colocation_distance_keeps_its_exact_point():
    cases = chain_plus(pair_x=COLOCATED_M + 5.0)
    out, result = exports(cases)
    zid = next(z.zombie_id for z in result.zombies if z.resurrection_id == "Q")
    card = card_of(out, zid)
    assert card["original"]["street"] == "30-32 Saint Germain St" and (card["original"]["lat"], card["original"]["lon"]) != MID


def test_req_exp_priv_1_a_zombie_on_another_segment_keeps_its_exact_point_even_5_m_away():
    cases = chain_plus(pair_segment="S_OTHER")
    out, result = exports(cases)
    zid = next(z.zombie_id for z in result.zombies if z.resurrection_id == "Q")
    assert card_of(out, zid)["original"]["street"] == "30-32 Saint Germain St"


def test_req_exp_priv_1_the_colocated_zombie_is_left_out_of_the_block_map_of_the_chain_itself():
    """The rule changes the exported rows of the colocated zombie only: it is not added to the chain's cases and no count
    moves."""
    cases = chain_plus()
    result = detect(cases)
    segs = {"S_RES": SegmentInfo(MID, "Local")}
    by_id = {c.id: c for c in cases}
    locations = block_level_locations(result, by_id, segs)
    block_of = block_location_by_case(result, locations)
    extra = colocated_block_locations(result, by_id, block_of)
    assert set(extra) == {"Q"} and extra["Q"] == MID
    assert "P" not in block_of and "Q" not in block_of
    assert colocated_block_locations(result, by_id, {}) == {}


def test_req_exp_priv_1_colocation_is_a_pure_function_of_the_data_not_of_the_row_order():
    cases = chain_plus()
    a, _ = exports(cases)
    b, _ = exports(list(reversed(cases)))
    assert a == b
