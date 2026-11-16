"""Hypothesis strategies: small generated towns for the detector properties (design.md "Correctness properties")."""

from __future__ import annotations

from dataclasses import replace

from helpers import mk
from hypothesis import strategies as st

LABELS = ["resolved", "noted", "invalid", "duplicate", "referred", "made_safe_temporary", "planned_followup", "other"]
SOURCES = ["Constituent Call", "Citizens Connect App", "Employee Generated", "City Worker App", "Maximo Integration", "BOS311"]
FAMILIES = ["pothole_roadway", "sign"]
XS = [0.0, 8.0, 21.0, 43.0, 71.0, 140.0]  # no pair of these is exactly 30 m or 75 m apart


@st.composite
def town(draw, min_size=2, max_size=22, families=FAMILIES):
    n = draw(st.integers(min_size, max_size))
    cases = []
    for i in range(n):
        cid = f"{draw(st.sampled_from(['C', 'D']))}{i:03d}"
        system = draw(st.sampled_from(["legacy", "new"]))
        open_h = draw(st.integers(0, 24 * 100))
        closed = draw(st.integers(0, 9)) < 7
        dur_h = draw(st.integers(1, 24 * 12))
        x = draw(st.sampled_from(XS))
        seg = draw(st.sampled_from([None, "mix"]))
        segment = None if seg is None else ("S1" if x <= 80 else "S2")
        label = draw(st.sampled_from(LABELS))
        code = None
        text = None
        if system == "new" and draw(st.integers(0, 9)) == 0:
            code = "Transitioned"
            label = "referred"
        if system == "legacy" and draw(st.integers(0, 9)) == 0:
            text = "Case Closed. Resubmitted as BCS-00000001"
            label = "referred"
        cases.append(
            mk(
                cid,
                open_h / 24,
                (open_h + dur_h) / 24 if closed else None,
                x=x,
                system=system,
                family=draw(st.sampled_from(families)),
                segment=segment,
                label=label,
                tier=draw(st.sampled_from(["core", "core", "core", "sensitivity"])),
                source=draw(st.sampled_from(SOURCES)),
                code=code,
                text=text,
                city_type=draw(st.integers(0, 9)) == 0,
            )
        )
    legacy_ids = [c.id for c in cases if c.system == "legacy"]
    out = []
    for c in cases:
        if c.system == "new" and legacy_ids and draw(st.integers(0, 4)) == 0:
            c = replace(c, predecessor_ids=(draw(st.sampled_from(legacy_ids)),), catch_all=True)
        out.append(c)
    return out
