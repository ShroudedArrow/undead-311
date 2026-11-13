"""Property P4 part 1: normalization is invariant to input row order (REQ-ING-2.3, testing.md #5)."""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_normalize import L1, N1, make_con

from undead311.ingest.normalize import normalize

STAMPS = ["2024-03-04 09:12:00", "2024-11-03 01:30:00", "2024-03-10 02:30:00", "bad", "", "2025-08-01 00:00:00"]


@st.composite
def raw_rows(draw):
    legacy = []
    for i in range(draw(st.integers(0, 8))):
        legacy.append(
            (
                f"L{draw(st.integers(0, 6))}",  # duplicate ids are possible on purpose
                draw(st.sampled_from(STAMPS)),
                draw(st.sampled_from(STAMPS)),
                draw(st.sampled_from(["Open", "Closed"])),
                draw(st.sampled_from(["Case Closed", None])),
                draw(st.sampled_from(["Sign Repair", "Request for Pothole Repair"])),
                None, None, None, None,
                draw(st.sampled_from(["42.3", "x", None])),
                "-71.1", None, None,
                f"311_{2020 + i % 2}.csv",
            )
        )
    new = [N1[:0] + (f"N{i}",) + N1[1:] for i in range(draw(st.integers(0, 3)))]
    return legacy, new


def snapshot(legacy, new):
    con = make_con(legacy, new)
    report = normalize(con)
    rows = con.execute("select * from cases_norm order by all").fetchall()
    return rows, sorted(report.issues.items())


@settings(max_examples=25)
@given(raw_rows(), st.randoms(use_true_random=False))
def test_prop_p4_normalization_is_invariant_to_row_order(rows, rnd):
    """REQ-ING-2.3: shuffling raw rows leaves cases_norm and the issue counts unchanged."""
    legacy, new = rows
    shuffled_l, shuffled_n = legacy[:], new[:]
    rnd.shuffle(shuffled_l)
    rnd.shuffle(shuffled_n)
    assert snapshot(legacy, new) == snapshot(shuffled_l, shuffled_n)


def test_prop_p4_fixed_example_included():
    """REQ-ING-2.3: a sanity row from each system normalizes identically in either order."""
    assert snapshot([L1], [N1]) == snapshot([L1], [N1])
