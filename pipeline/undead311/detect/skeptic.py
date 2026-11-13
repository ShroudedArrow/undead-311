"""Skeptic input and join (REQ-SKEP).

`build_input` selects the zombies the Skeptic agent reviews: the validation sample, every zombie in the judge tour
(provisional or confirmed), and the `top_n` (200) headline zombies with the most re-reports. Selection never uses the
confidence score (REQ-SKEP.1); ties are broken by zombie ID. `join_objections` reads
`data/labels/skeptic_objections.json` (a list, or {"objections": [...]}, of
{incident_id, resurrection_id, verdict, notes}) into `skeptic_verdict` and `skeptic_notes`; a zombie with no review
keeps `not_reviewed` (REQ-SKEP.2).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from undead311.detect.confidence import rescore
from undead311.detect.model import Case, Zombie
from undead311.detect.params import DEFAULT, Params
from undead311.ingest.pii import scrub_text

VERDICTS = ("survives", "weakened", "explained_away", "not_reviewed")
TOP_N = 200


def select_for_review(
    zombies: Iterable[Zombie], validation_ids: Iterable[str] = (), tour_ids: Iterable[str] = (), top_n: int = TOP_N
) -> dict[str, list[str]]:
    """zombie_id -> reasons ('validation_sample', 'judge_tour', 'top_reports'); never ranked by confidence."""
    zombies = list(zombies)
    known = {z.zombie_id for z in zombies}
    reasons: dict[str, list[str]] = {}
    for zid in sorted(set(validation_ids) & known):
        reasons.setdefault(zid, []).append("validation_sample")
    for zid in sorted(set(tour_ids) & known):
        reasons.setdefault(zid, []).append("judge_tour")
    headline = [z for z in zombies if z.tier == "headline"]
    for z in sorted(headline, key=lambda z: (-z.reports_after, z.zombie_id))[:top_n]:
        reasons.setdefault(z.zombie_id, []).append("top_reports")
    return reasons


def _case_view(c: Case) -> dict:
    return {
        "id": c.id,
        "system": c.system,
        "open_time": c.open_utc.isoformat(),
        "close_time": c.close_utc.isoformat() if c.close_utc else None,
        "type_raw": c.type_raw,
        "status": c.status,
        "closure_text": scrub_text(c.closure_text),
        "street": c.street,
        "lat": c.lat,
        "lon": c.lon,
    }


def build_input(
    zombies: Iterable[Zombie],
    cases: Mapping[str, Case],
    data_version: str,
    validation_ids: Iterable[str] = (),
    tour_ids: Iterable[str] = (),
    top_n: int = TOP_N,
) -> dict:
    zombies = list(zombies)
    reasons = select_for_review(zombies, validation_ids, tour_ids, top_n)
    items = []
    for z in sorted(zombies, key=lambda z: z.zombie_id):
        if z.zombie_id not in reasons:
            continue
        items.append(
            {
                "zombie_id": z.zombie_id,
                "incident_id": z.incident_id,
                "resurrection_id": z.resurrection_id,
                "reasons": sorted(reasons[z.zombie_id]),
                "type_family": z.type_family,
                "tier": z.tier,
                "gap_days": round(z.gap_days, 4),
                "match_mode": z.match_mode,
                "distance_m": round(z.distance_m, 2),
                "reports_after": z.reports_after,
                "coroner_label": z.coroner_label,
                "original": [_case_view(cases[m]) for m in z.member_ids if m in cases],
                "rereport": _case_view(cases[z.resurrection_id]) if z.resurrection_id in cases else None,
            }
        )
    return {"data_version": data_version, "items": items}


def write_input(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return path


def load_objections(path: Path | None) -> dict[tuple[str, str], tuple[str, str]]:
    """(incident_id, resurrection_id) -> (verdict, notes). A missing file gives {}."""
    if path is None or not Path(path).is_file():
        return {}
    raw = json.loads(Path(path).read_text())
    rows = raw["objections"] if isinstance(raw, dict) else raw
    out = {}
    for r in rows:
        verdict = r["verdict"]
        if verdict not in VERDICTS or verdict == "not_reviewed":
            raise ValueError(f"skeptic verdict {verdict!r} must be one of survives, weakened, explained_away")
        out[(r["incident_id"], r["resurrection_id"])] = (verdict, scrub_text(r.get("notes", "")) or "")
    return out


def join_objections(zombies: Iterable[Zombie], path: Path | None, p: Params = DEFAULT) -> list[Zombie]:
    """Join the objections by (incident ID, resurrection ID) and rescore (REQ-SKEP.2)."""
    objections = load_objections(path)
    out = []
    for z in zombies:
        hit = objections.get((z.incident_id, z.resurrection_id))
        out.append(rescore(z, p, skeptic_verdict=hit[0], skeptic_notes=hit[1]) if hit else z)
    return out
