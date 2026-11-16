"""REQ-DET-GOLD.1-5: the detector must reproduce the owner's hand-written answer for the test town exactly.

The answer key `pipeline/tests/fixtures/expected_zombies.json` is written by the project owner and is only read here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from undead311.fixtures import (
    COMPARED_KEYS,
    FIXTURE,
    METADATA_KEYS,
    golden_result,
    load_test_town,
    run_test_town,
)

EXPECTED = Path(__file__).resolve().parents[1] / "fixtures" / "expected_zombies.json"


def _expected(path: Path | None = None) -> dict:
    path = path or EXPECTED
    if not path.is_file():
        pytest.fail("answer key missing: the owner writes it by hand (pipeline/tests/fixtures/expected_zombies.json)")
    return json.loads(path.read_text())


def test_req_det_gold_2_missing_answer_key_fails_and_never_skips(tmp_path):
    """REQ-DET-GOLD.2: with no answer key the golden test fails with the stated message (it is never skipped)."""
    with pytest.raises(pytest.fail.Exception, match="answer key missing: the owner writes it by hand"):
        _expected(tmp_path / "nope.json")


def test_req_det_gold_5_expected_keys_are_known():
    """REQ-DET-GOLD.5: an unknown key in the answer key fails the test; a key left out is not compared."""
    unknown = set(_expected()) - set(COMPARED_KEYS) - set(METADATA_KEYS)
    assert not unknown, f"unknown keys in expected_zombies.json: {sorted(unknown)}"


@pytest.mark.parametrize("key", COMPARED_KEYS)
def test_req_det_gold_1_5_detector_reproduces_expected_zombies_json(key):
    """REQ-DET-GOLD.1, .5: crosswalk, catch-all, clean and detect on the raw fixture rows equal the answer key."""
    expected = _expected()
    if key not in expected:
        pytest.skip(f"owner left {key!r} out of expected_zombies.json (REQ-DET-GOLD.5: not compared)")
    result, excluded = run_test_town()
    assert golden_result(result, excluded)[key] == expected[key]


def test_req_det_gold_4_fixture_loader_ignores_scenario_and_note_columns():
    """REQ-DET-GOLD.4: the loader's table has the normalized schema only; the label column is the fixture's own."""
    import duckdb

    con = duckdb.connect()
    load_test_town(con, FIXTURE)
    cols = {r[0] for r in con.execute("describe cases_norm").fetchall()}
    assert not cols & {"scenario", "note"} and "coroner_label" in cols
    assert con.execute("select count(*) from cases_norm").fetchone()[0] == 75
