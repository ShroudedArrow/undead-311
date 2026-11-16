"""REQ-ING-2, ops#214: street names with "&" reach every table and card as "&", never as "&amp;"."""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
from hypothesis import given
from hypothesis import strategies as st

from tests.unit.test_normalize import L1, N1, make_con
from undead311.detect.cases import cases_from_sample_csv
from undead311.ingest.normalize import normalize
from undead311.ingest.text import decode_entities, register_text_udfs

ESCAPED = "INTERSECTION Call St &amp; Carolina Ave"
PLAIN = "INTERSECTION Call St & Carolina Ave"


def test_req_ing_2_decode_entities_turns_amp_into_ampersand():
    """REQ-ING-2 (ops#214): one level is decoded; plain text, "" and None pass through unchanged."""
    assert decode_entities(ESCAPED) == PLAIN
    assert decode_entities(PLAIN) == PLAIN  # an "&" that is already plain stays as it is
    assert decode_entities("Washington St &amp;amp; Snow St") == "Washington St &amp; Snow St"  # one level only
    assert decode_entities("") == ""
    assert decode_entities(None) is None


@given(st.text(alphabet=st.characters(blacklist_characters="&"), max_size=40))
def test_req_ing_2_text_without_ampersand_is_unchanged(text):
    """REQ-ING-2 (ops#214): only text with "&" can change."""
    assert decode_entities(text) == text


def test_req_ing_2_udf_registers_twice_without_error():
    con = duckdb.connect()
    register_text_udfs(con)
    register_text_udfs(con)
    assert con.execute("select undead_unescape(?)", [ESCAPED]).fetchone()[0] == PLAIN
    assert con.execute("select undead_unescape(NULL)").fetchone()[0] is None


def test_req_ing_2_normalize_decodes_street_in_both_systems():
    """REQ-ING-2 (ops#214): the full-data normalizer stores "&" for legacy and new-system street names."""
    legacy = L1[:9] + (ESCAPED,) + L1[10:]
    new = N1[:10] + ("Call St &amp; Carolina Ave",) + N1[11:]
    con = make_con([legacy], [new])
    normalize(con)
    streets = dict(con.execute("select id, street from cases_norm").fetchall())
    assert streets == {"1001": PLAIN, "BCS-00000001": "Call St & Carolina Ave"}


def test_req_ing_2_sample_loader_decodes_street(tmp_path: Path):
    """REQ-ING-2 (ops#214): the committed sample keeps the city's "&amp;"; the sample loader decodes it."""
    sample = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample_311.csv"
    with sample.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = [r for _, r in zip(range(5), reader)]
    rows[0]["street"] = ESCAPED
    path = tmp_path / "s.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    by_id = {c.id: c for c in cases_from_sample_csv(path)}
    assert by_id[rows[0]["id"]].street == PLAIN
    assert not any(c.street and "&amp;" in c.street for c in by_id.values())
