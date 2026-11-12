"""Checks on the committed data/sample/sample_311.csv (REQ-ING-SAMPLE, REQ-ING-TZ)."""

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from undead311.ingest.closure_flags import is_mirror_pair, is_transfer_closure, pair_survives
from undead311.ingest.times import to_utc_and_local

SAMPLE = Path(__file__).parents[3] / "data" / "sample" / "sample_311.csv"
EXCLUDED_FAMILIES = {"graffiti", "missed_trash", "abandoned_vehicle", "street_litter"}
EXCLUDED_TYPES = {"Catchbasin", "Traffic Signal Inspection", "Pavement Marking Inspection", "General Lighting Request"}


@pytest.fixture(scope="module")
def rows():
    with SAMPLE.open(newline="") as f:
        return list(csv.DictReader(f))


def utc(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def test_size_under_10mb():
    assert SAMPLE.stat().st_size < 10_000_000


def test_columns_and_scope(rows):
    assert {"open_time_utc", "open_time_local", "local_ambiguous", "city_originated_type"} <= set(rows[0])
    assert {r["scope_tier"] for r in rows} == {"core"}
    assert not {r["type_family"] for r in rows} & EXCLUDED_FAMILIES
    assert not {r["type_raw"] for r in rows} & EXCLUDED_TYPES


def test_utc_matches_local(rows):
    for r in rows[::7]:
        local = datetime.fromisoformat(r["open_time_local"])
        got_utc, got_local, _ = to_utc_and_local(local)
        assert got_utc == utc(r["open_time_utc"])
        assert got_local == local


def test_cross_system_pairs_survive(rows):
    by_id = {(r["system"], r["id"]): r for r in rows}
    legacy = [r for r in rows if r["system"] == "legacy" and r["close_time_utc"]]
    new = [r for r in rows if r["system"] == "new"]
    cell = lambda r: (round(float(r["lat"]) / 0.0003), round(float(r["lon"]) / 0.0003))
    idx = {}
    for b in new:
        idx.setdefault((cell(b), b["type_family"]), []).append(b)
    assert by_id
    survivors = 0
    for a in legacy:
        for b in idx.get((cell(a), a["type_family"]), []):
            gap = (utc(b["open_time_utc"]) - utc(a["close_time_utc"])).total_seconds()
            if not 0 < gap <= 60 * 86400:
                continue
            ra = {**a, "open_utc": utc(a["open_time_utc"]), "closure_text": a["closure_text"]}
            rb = {**b, "open_utc": utc(b["open_time_utc"])}
            if pair_survives(ra, rb):
                survivors += 1
                assert not is_transfer_closure(a["closure_text"])
                assert not is_mirror_pair("legacy", "new", ra["open_utc"], rb["open_utc"], True, True)
    assert survivors >= 250


def test_traffic_signal_request_and_closure_code(rows):
    """REQ-ING-MIRROR / scope: sensitivity-tier types stay out of the core sample; Transitioned is never an original."""
    assert "closure_code" in rows[0]
    assert "Traffic Signal Request" not in {r["type_raw"] for r in rows}
    assert {r["scope_tier"] for r in rows} == {"core"}
    assert all(r["closure_code"] == "" for r in rows if r["system"] == "legacy")
    transitioned = [r for r in rows if r["closure_code"] == "Transitioned"]
    assert transitioned
    for r in transitioned:
        a = {**r, "open_utc": utc(r["open_time_utc"])}
        b = {**r, "open_utc": utc(r["open_time_utc"]), "system": "new"}
        assert not pair_survives(a, b)
