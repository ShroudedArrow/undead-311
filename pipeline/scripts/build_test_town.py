"""Write pipeline/tests/fixtures/test_town.csv, the golden "test town" CASES (testing.md).

The cases are drafted by Kiro from the scenario list in testing.md. The ANSWER KEY
(pipeline/tests/fixtures/expected_zombies.json) is written by hand by the project owner, never by this
script or any agent (the guard hook blocks agent edits to it). See docs/TEST_TOWN_WORKSHEET.md.

Input contract: normalized-schema rows BEFORE family resolution. The engine derives type_family, scope_tier,
city_originated_type, catch-all inheritance and predecessor_ids itself from type_families.csv and the
closure texts. Extra fixture-only columns:
  segment_id, segment_snap_m  pre-snapped SAM street segment (blank = no segment within 15 m), so the
                              fixture does not need the SAM layer;
  coroner_label               the Coroner label of the closure, so the answer does not depend on the label table;
  scenario, note              for the worksheet; the detector must ignore them.
Each scenario sits at its own spot (at least 800 m from every other) so scenarios cannot interact.
Run: `uv run python pipeline/scripts/build_test_town.py` (deterministic).
"""

from __future__ import annotations

import csv
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from undead311.ingest.times import to_utc_and_local

OUT = ROOT / "pipeline" / "tests" / "fixtures" / "test_town.csv"
COLUMNS = [
    "id", "system", "open_time_utc", "close_time_utc", "open_time_local", "close_time_local", "local_ambiguous",
    "status", "closure_text", "closure_code", "type_raw", "department", "neighborhood", "street", "lat", "lon",
    "source", "segment_id", "segment_snap_m", "coroner_label", "scenario", "note",
]
PLACEHOLDERS = [(42.3603, -71.0583), (42.3595, -71.0588)]
M_PER_DEG_LAT = 111_132.0

# scenario spots: a grid across Boston (>= 800 m between scenarios, > 6 km from the placeholder points)
NEIGHBORHOODS = ["Dorchester", "Roxbury", "Jamaica Plain", "Mattapan", "Roslindale", "Hyde Park", "West Roxbury",
                 "South Boston", "East Boston", "Charlestown", "Brighton", "Allston", "Fenway", "South End",
                 "Mission Hill", "Back Bay", "Beacon Hill", "Dorchester", "Roxbury", "Jamaica Plain"]


def spot(s: int) -> tuple[float, float]:
    i, j = divmod(s - 1, 5)
    return 42.270 + 0.012 * i, -71.140 + 0.016 * j


def offset(base: tuple[float, float], east_m: float, north_m: float) -> tuple[float, float]:
    lat, lon = base
    return (round(lat + north_m / M_PER_DEG_LAT, 6),
            round(lon + east_m / (M_PER_DEG_LAT * math.cos(math.radians(lat))), 6))


def lid(s: int, n: int) -> str:
    return f"1010990{s:02d}{n:03d}"


def nid(s: int, n: int) -> str:
    return f"BCS-009{s:02d}{n:03d}"


def stamp(local: str | None) -> tuple[str, str, bool]:
    if not local:
        return "", "", False
    utc, loc, flags = to_utc_and_local(datetime.fromisoformat(local))
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ"), loc.strftime("%Y-%m-%dT%H:%M:%S"), bool(flags)


ROWS: list[dict] = []


def case(s, n, system, opened, closed, type_raw, *, at=(0, 0), text="", code="", label="", source="", seg="a",
         snap=4.0, street="", dept="", note="", latlon=None, cid=None):
    base = spot(s)
    lat, lon = latlon if latlon is not None else offset(base, *at)
    o_utc, o_loc, o_amb = stamp(opened)
    c_utc, c_loc, c_amb = stamp(closed)
    ROWS.append({
        "id": cid or (lid(s, n) if system == "legacy" else nid(s, n)),
        "system": system,
        "open_time_utc": o_utc, "close_time_utc": c_utc, "open_time_local": o_loc, "close_time_local": c_loc,
        "local_ambiguous": str(o_amb or c_amb).lower(),
        "status": "Closed" if closed else "Open",
        "closure_text": text, "closure_code": code, "type_raw": type_raw,
        "department": dept or ("PWDx" if system == "legacy" else "PWD"),
        "neighborhood": NEIGHBORHOODS[(s - 1) % len(NEIGHBORHOODS)],
        "street": street or f"Test St {s}",
        "lat": "" if lat is None else f"{lat:.6f}", "lon": "" if lon is None else f"{lon:.6f}",
        "source": source or ("Constituent Call" if system == "legacy" else "BOS311"),
        "segment_id": f"SEG-{s:02d}-{seg}" if seg else "", "segment_snap_m": f"{snap:.1f}" if seg else "",
        "coroner_label": label if closed else "",
        "scenario": f"S{s:02d}", "note": note,
    })


RES = "Case Closed Case Resolved Pothole repaired"
MADE_SAFE = ("Case Closed Case Resolved This location has been inspected and where possible temporary repairs or "
             "safety measures have been made")


def build() -> None:
    # S01 true zombies (one per system)
    case(1, 1, "legacy", "2024-03-04 09:12:00", "2024-03-06 14:30:00", "Request for Pothole Repair", text=RES,
         label="resolved", source="Citizens Connect App", note="original")
    case(1, 2, "legacy", "2024-03-26 10:05:00", None, "Request for Pothole Repair", at=(10, 0),
         source="Citizens Connect App", note="re-report 20 days after closure, 10 m away, same segment")
    case(1, 3, "new", "2026-04-06 08:40:00", "2026-04-08 13:00:00", "Sidewalk Repair", at=(0, 400), seg="b",
         text="Sidewalk panel replaced", code="Resolved", label="resolved", note="original (new system)")
    case(1, 4, "new", "2026-04-23 17:20:00", None, "Sidewalk Repair", at=(12, 400), seg="b",
         note="re-report 15 days after closure, 12 m away")
    # S02 coincidences that must not match
    case(2, 1, "legacy", "2024-04-01 08:00:00", "2024-04-02 12:00:00", "Request for Pothole Repair", text=RES,
         label="resolved", note="original")
    case(2, 2, "legacy", "2024-06-02 12:30:00", "2024-06-04 09:00:00", "Request for Pothole Repair", at=(5, 0),
         text=RES, label="resolved", note="61 days after closure: outside WINDOW_DAYS = 60")
    case(2, 3, "legacy", "2024-04-10 09:00:00", "2024-04-11 15:00:00", "Sign Repair", at=(0, 500), seg="",
         text="Case Closed Case Resolved Sign replaced", label="resolved", dept="BTDT", note="original, no segment")
    case(2, 4, "legacy", "2024-04-21 11:00:00", None, "Sign Repair", at=(45, 500), seg="", dept="BTDT",
         note="10 days later but 45 m away, no segment: outside RADIUS_M = 30")
    # S03 duplicate reports form ONE incident, then one re-report
    for n, (o, c, e) in enumerate([("2024-05-06 08:00:00", "2024-05-08 10:00:00", 0),
                                   ("2024-05-06 15:00:00", "2024-05-08 10:05:00", 6),
                                   ("2024-05-07 09:00:00", "2024-05-08 10:10:00", -5)], 1):
        case(3, n, "legacy", o, c, "Street Light Outages", at=(e, 0), text="Case Closed Case Resolved Lamp replaced",
             label="resolved", note="duplicate report, opened before the first closure")
    case(3, 4, "legacy", "2024-05-28 19:00:00", None, "Street Light Outages", at=(3, 3),
         note="re-report 20 days after the incident closed")
    # S04 planned follow-ups (city-originated R after made safe / referred)
    case(4, 1, "legacy", "2024-06-03 07:30:00", "2024-06-03 11:00:00", "Sidewalk Repair (Make Safe)", text=MADE_SAFE,
         label="made_safe_temporary", note="original, made safe")
    case(4, 2, "legacy", "2024-06-13 07:00:00", "2024-06-20 15:00:00", "Sidewalk Repair", at=(4, 0),
         source="Employee Generated", text="Case Closed Case Resolved Sidewalk replaced", label="resolved",
         note="city-originated by source, 10 days later")
    case(4, 3, "legacy", "2024-07-08 09:00:00", "2024-07-09 10:00:00", "Sidewalk Repair", at=(0, 450), seg="b",
         text="Case Closed Case Resolved Referred to BWSC for repair", label="referred", note="original, referred")
    case(4, 4, "legacy", "2024-07-22 06:45:00", None, "Sidewalk Repair (Internal)", at=(6, 450), seg="b",
         note="city-originated by type (Internal), source looks like a resident")
    # S05 three-time repeat offender chain
    chain = [("2024-01-02 08:00:00", "2024-01-05 12:00:00"), ("2024-01-20 18:30:00", "2024-01-25 10:00:00"),
             ("2024-02-15 07:10:00", "2024-02-18 16:00:00"), ("2024-03-20 21:00:00", None)]
    for n, (o, c) in enumerate(chain, 1):
        case(5, n, "legacy", o, c, "Street Light Outages", at=(2 * n, 0),
             text="Case Closed Case Resolved Lamp replaced" if c else "", label="resolved" if c else "",
             note=["original", "re-report 1", "re-report 2", "re-report 3 (still open)"][n - 1])
    # S06 placeholder and invalid coordinates
    case(6, 1, "legacy", "2024-08-05 09:00:00", "2024-08-06 09:00:00", "Request for Pothole Repair",
         latlon=PLACEHOLDERS[0], seg="", text=RES, label="resolved", note="placeholder point 1")
    case(6, 2, "legacy", "2024-08-20 09:00:00", None, "Request for Pothole Repair", latlon=PLACEHOLDERS[0], seg="",
         note="placeholder point 1 again, within the window")
    case(6, 3, "new", "2026-02-09 10:00:00", "2026-02-10 10:00:00", "Pothole", latlon=PLACEHOLDERS[1], seg="",
         text="Pothole filled", code="Resolved", label="resolved", note="placeholder point 2")
    case(6, 4, "legacy", "2024-08-07 09:00:00", "2024-08-08 09:00:00", "Request for Pothole Repair",
         latlon=(42.0, -72.0), seg="", text=RES, label="resolved", note="out-of-bounds coordinates")
    # S07 out-of-scope types
    case(7, 1, "legacy", "2024-09-02 10:00:00", "2024-09-03 10:00:00", "Graffiti Removal",
         text="Case Closed Case Resolved Graffiti removed", label="resolved", note="excluded event type")
    case(7, 2, "legacy", "2024-09-15 10:00:00", None, "Graffiti Removal", at=(3, 0), note="graffiti again")
    case(7, 3, "legacy", "2024-09-09 08:00:00", "2024-09-09 12:00:00", "Encampments", at=(0, 500), seg="b",
         text="Case Closed Case Resolved", label="resolved", note="people-related type")
    case(7, 4, "legacy", "2024-09-19 08:00:00", None, "Encampments", at=(4, 500), seg="b", note="people-related again")
    # S08 pairs spanning the 2025 system change
    case(8, 1, "legacy", "2025-09-08 08:15:00", "2025-09-15 13:00:00", "Request for Pothole Repair", text=RES,
         label="resolved", note="legacy original, normal closure")
    case(8, 2, "new", "2025-10-05 09:30:00", None, "Pothole", at=(8, 0), note="new-system re-report 20 days later")
    case(8, 3, "legacy", "2025-08-18 10:00:00", "2025-08-20 11:00:00", "Sign Repair", at=(0, 450), seg="b",
         text="Case Closed Case Resolved Sign replaced", label="resolved", dept="BTDT", note="legacy original")
    case(8, 4, "new", "2025-09-19 14:00:00", None, "Damaged/Faded Sign", at=(5, 450), seg="b", dept="BTD",
         note="new-system re-report 30 days later (crosswalk family sign)")
    # S09 fast resurrection vs. a true duplicate
    case(9, 1, "legacy", "2024-10-07 08:00:00", "2024-10-07 16:00:00", "Request for Pothole Repair", text=RES,
         label="resolved", note="original")
    case(9, 2, "legacy", "2024-10-08 09:00:00", "2024-10-10 15:00:00", "Request for Pothole Repair", at=(3, 0),
         text=RES, label="resolved", note="re-reported next day, closed within 3 days")
    case(9, 3, "legacy", "2024-11-04 08:00:00", "2024-11-04 18:00:00", "Request for Pothole Repair", at=(0, 450),
         seg="b", text=RES, label="resolved", note="contrast: original")
    case(9, 4, "legacy", "2024-11-04 14:00:00", "2024-11-05 10:00:00", "Request for Pothole Repair", at=(4, 450),
         seg="b", text=RES, label="resolved", note="contrast: opened BEFORE the first closure (duplicate)")
    # S10 one long segment: opposite ends vs. 60 m apart
    case(10, 1, "legacy", "2024-02-05 09:00:00", "2024-02-07 09:00:00", "Request for Pothole Repair", text=RES,
         label="resolved", snap=3.0, street="Long Ave", note="west end of a long segment")
    case(10, 2, "legacy", "2024-02-20 09:00:00", None, "Request for Pothole Repair", at=(300, 0), snap=5.0,
         street="Long Ave", note="east end, same segment, 300 m away (> MAX_SEGMENT_DIST = 75)")
    case(10, 3, "legacy", "2024-03-11 09:00:00", "2024-03-12 09:00:00", "Request for Pothole Repair", at=(0, 500),
         seg="b", snap=6.0, text=RES, label="resolved", street="Short Ave", note="contrast: original")
    case(10, 4, "legacy", "2024-03-25 09:00:00", None, "Request for Pothole Repair", at=(60, 500), seg="b", snap=7.0,
         street="Short Ave", note="contrast: same segment, 60 m away (> RADIUS_M, <= MAX_SEGMENT_DIST)")
    # S11 resident re-report after a made-safe closure
    case(11, 1, "legacy", "2024-04-15 08:00:00", "2024-04-15 13:00:00", "Sidewalk Repair (Make Safe)",
         text=MADE_SAFE, label="made_safe_temporary", note="original, made safe")
    case(11, 2, "legacy", "2024-04-29 18:00:00", None, "Sidewalk Repair", at=(5, 0), source="Constituent Call",
         note="resident re-report 14 days later")
    case(11, 3, "legacy", "2024-05-13 09:00:00", "2024-05-13 15:00:00", "Request for Pothole Repair", at=(0, 450),
         seg="b", text=MADE_SAFE, label="made_safe_temporary", note="original, made safe")
    case(11, 4, "legacy", "2024-05-30 12:00:00", None, "Request for Pothole Repair", at=(7, 450), seg="b",
         source="Citizens Connect App", note="resident (app) re-report 17 days later")
    # S12 legacy transferred originals
    case(12, 1, "legacy", "2025-09-22 08:00:00", "2025-10-14 10:30:00", "Request for Pothole Repair",
         text=f"Case Closed Case Resolved Resubmitted as {nid(12, 2)}", label="referred",
         note="legacy closed as a transfer at migration")
    case(12, 2, "new", "2025-10-14 10:27:00", "2025-10-20 12:00:00", "Pothole", at=(2, 0), text="Pothole filled",
         code="Resolved", label="resolved", note="its new-system successor (opened 3 min before the legacy close)")
    case(12, 3, "legacy", "2025-10-01 09:00:00", "2025-10-03 09:00:00", "Sign Repair", at=(0, 450), seg="b",
         text="Case Closed case transferred to BTD", label="referred", dept="BTDT",
         note="legacy transfer closure with no case link")
    case(12, 4, "new", "2025-10-08 11:00:00", None, "Knocked Down Sign", at=(6, 450), seg="b", dept="BTD",
         note="new-system sign report 5 days later")
    # S13 new-system re-report with unknown source
    case(13, 1, "new", "2026-03-02 08:00:00", "2026-03-02 14:00:00", "Sidewalk Repair",
         text="Temporary patch installed; area made safe", code="Resolved", label="made_safe_temporary",
         note="new-system original, made safe")
    case(13, 2, "new", "2026-03-14 10:00:00", None, "Sidewalk Repair", at=(5, 0), source="Call",
         note="new-system re-report 12 days later (origin unknown)")
    case(13, 3, "new", "2026-04-13 09:00:00", "2026-04-14 09:00:00", "Pothole", at=(0, 450), seg="b",
         text="Referred to utility company for repair", code="Resolved", label="referred",
         note="new-system original referred by closure text (code Resolved)")
    case(13, 4, "new", "2026-04-30 16:00:00", None, "Pothole", at=(4, 450), seg="b",
         note="new-system re-report 16 days later")
    # S14 mirror copies (cross-system, opened within 6 h)
    case(14, 1, "legacy", "2025-09-10 08:00:00", "2025-09-10 09:00:00", "Request for Pothole Repair", text=RES,
         label="resolved", note="legacy report")
    case(14, 2, "new", "2025-09-10 11:00:00", "2025-09-12 10:00:00", "Pothole", at=(4, 0), text="Pothole filled",
         code="Resolved", label="resolved", note="new-system copy opened 3 h after the legacy one")
    case(14, 3, "new", "2025-10-06 07:30:00", "2025-10-06 08:15:00", "Street Light Outage", at=(0, 450), seg="b",
         text="Lamp replaced", code="Resolved", label="resolved", note="new-system report")
    case(14, 4, "legacy", "2025-10-06 12:00:00", "2025-10-07 09:00:00", "Street Light Outages", at=(3, 450), seg="b",
         text="Case Closed Case Resolved Lamp replaced", label="resolved",
         note="legacy copy opened 4.5 h after the new one")
    # S15 same-system fast re-reports (mirror rule does not apply)
    case(15, 1, "legacy", "2024-05-06 08:00:00", "2024-05-06 09:00:00", "Request for Pothole Repair", text=RES,
         label="resolved", note="closed 1 h after it opened")
    case(15, 2, "legacy", "2024-05-06 13:00:00", None, "Request for Pothole Repair", at=(3, 0),
         note="re-reported 5 h after the original opened")
    case(15, 3, "new", "2026-05-04 08:00:00", "2026-05-04 09:00:00", "Pothole", at=(0, 450), seg="b",
         text="Pothole filled", code="Resolved", label="resolved", note="closed 1 h after it opened")
    case(15, 4, "new", "2026-05-04 13:00:00", None, "Pothole", at=(3, 450), seg="b",
         note="re-reported 5 h after the original opened")
    # S16 new-system Transitioned vs. Noted closures
    case(16, 1, "new", "2026-06-01 09:00:00", "2026-06-02 09:00:00", "Pothole", text="Transitioned to BWSC",
         code="Transitioned", label="referred", note="closure code Transitioned")
    case(16, 2, "new", "2026-06-12 09:00:00", None, "Pothole", at=(4, 0), note="re-report 10 days later")
    case(16, 3, "new", "2026-06-08 09:00:00", "2026-06-09 09:00:00", "Pothole", at=(0, 450), seg="b",
         text="Case noted", code="Noted", label="noted", note="contrast: closure code Noted")
    case(16, 4, "new", "2026-06-19 09:00:00", None, "Pothole", at=(4, 450), seg="b", note="re-report 10 days later")
    # S17 linked catch-all (Street Light Other inherits the legacy family)
    case(17, 1, "legacy", "2025-11-03 08:00:00", "2025-11-20 10:00:00", "Request for Pothole Repair",
         text=f"Case Closed. Resubmitted as {nid(17, 2)}", label="referred", note="legacy pothole closed as a transfer")
    case(17, 2, "new", "2025-11-20 09:57:00", "2025-11-25 11:00:00", "Street Light Other", at=(2, 0),
         text="Pothole filled", code="Resolved", label="resolved",
         note="linked successor: inherits pothole_roadway / core from 101099017001")
    case(17, 3, "new", "2025-12-15 08:30:00", None, "Pothole", at=(5, 0),
         note="resident pothole re-report 20 days after the successor closed")
    # S18 sensitivity tier: unlinked catch-all and Traffic Signal Request
    case(18, 1, "new", "2026-02-02 09:00:00", "2026-02-04 09:00:00", "Street Light Other", text="Fixture repaired",
         code="Resolved", label="resolved", note="unlinked Street Light Other")
    case(18, 2, "new", "2026-02-20 09:00:00", None, "Street Light Other", at=(4, 0), note="unlinked, 16 days later")
    case(18, 3, "new", "2026-03-02 09:00:00", "2026-03-03 09:00:00", "Traffic Signal Request", at=(0, 450), seg="b",
         text="Signal head repaired", code="Resolved", label="resolved", dept="BTD", note="sensitivity-only type")
    case(18, 4, "new", "2026-03-15 09:00:00", None, "Traffic Signal Request", at=(5, 450), seg="b", dept="BTD",
         note="sensitivity-only type, 12 days later")
    # S19 invalid and duplicate closures (zombie-definition step 8)
    case(19, 1, "legacy", "2024-06-10 09:00:00", "2024-06-10 15:00:00", "Request for Pothole Repair",
         text="Case Closed Case Invalid This case has been closed as there is not enough information",
         label="invalid", note="closed invalid")
    case(19, 2, "legacy", "2024-06-15 09:00:00", None, "Request for Pothole Repair", at=(3, 0),
         note="re-report 5 days later")
    case(19, 3, "legacy", "2024-07-01 09:00:00", "2024-07-01 12:00:00", "Sign Repair", at=(0, 450), seg="b",
         text="Case Closed Case Resolved Duplicate of Existing Case 101005000000", label="duplicate", dept="BTDT",
         note="closed duplicate")
    case(19, 4, "legacy", "2024-07-09 09:00:00", None, "Sign Repair", at=(4, 450), seg="b", dept="BTDT",
         note="re-report 8 days later")


def main() -> None:
    build()
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)), "duplicate case id"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(ROWS, key=lambda r: (r["scenario"], r["id"])))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(ROWS)} cases")


if __name__ == "__main__":
    main()
