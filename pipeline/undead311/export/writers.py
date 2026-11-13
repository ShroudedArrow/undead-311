"""Schema-validated, deterministic exports (REQ-EXP-1, REQ-ING-PII).

Every payload is validated against `schemas/<name>.schema.json` BEFORE anything is written; one invalid record refuses the
whole export (REQ-EXP-1.1). JSON is written with sorted keys and sorted records, so the same input gives byte-identical
files (REQ-EXP-1.3). Each file is written to a temporary name and renamed. `status.json` is written last (REQ-EXP-1.1),
so a failed run never leaves a status that claims success. Free text goes through the PII scrub (REQ-ING-PII.1).
`write_duckdb_atomic` builds the DuckDB file beside the target and renames it (REQ-EXP-1.4).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb
from jsonschema import Draft202012Validator

from undead311.detect.model import Case, DetectionResult, Zombie
from undead311.detect.params import DEFAULT, Params
from undead311.ingest.pii import scrub_text
from undead311.paths import repo_root

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"
EXCLUDED_ID_CAP = 5000


class ContractError(ValueError):
    """A payload does not validate against its JSON Schema (REQ-EXP-1.1)."""


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


def validate(name: str, payload: Any) -> None:
    errors = sorted(Draft202012Validator(load_schema(name)).iter_errors(payload), key=lambda e: list(map(str, e.path)))
    if errors:
        e = errors[0]
        where = "/".join(map(str, e.path)) or "<root>"
        raise ContractError(f"{name}: {e.message} (at {where}; {len(errors)} error(s))")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def data_version(snapshot_date: str, params: Params = DEFAULT, start: Path | None = None) -> str:
    """`<snapshot date>+<short git SHA>+<parameter hash>` (REQ-EXP-1.2)."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=start or repo_root(), capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "nogit"
    ph = hashlib.sha1(json.dumps(asdict(params), sort_keys=True).encode()).hexdigest()[:8]
    return f"{snapshot_date}+{sha}+{ph}"


def snapshot_date(snapshot_md: Path) -> str:
    m = re.search(r"Downloaded:\s*(\d{4}-\d{2}-\d{2})", snapshot_md.read_text()) if snapshot_md.is_file() else None
    return m.group(1) if m else "unknown"


def slug(text: str | None) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "unknown").lower()).strip("-")
    return s or "unknown"


@dataclass
class ExportContext:
    data_version: str
    run_time: str
    row_counts: dict[str, int] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)
    segments: str = "missing"
    exclusion_counts: dict[str, int] = field(default_factory=dict)
    excluded_ids: dict[str, list[str]] = field(default_factory=dict)
    bulk_closures: list[dict] = field(default_factory=list)
    stats_status: Mapping[str, Any] | None = None
    data_end: str | None = None


def zombie_record(z: Zombie) -> dict:
    return {
        "zombie_id": z.zombie_id, "incident_id": z.incident_id, "resurrection_id": z.resurrection_id,
        "reports_after": z.reports_after, "gap_days": round(z.gap_days, 6), "match_mode": z.match_mode,
        "distance_m": round(z.distance_m, 3), "tier": z.tier, "baseline_p": z.baseline_p,
        "confidence": round(z.confidence, 6), "confidence_partial": z.confidence_partial,
        "is_planned_followup": z.is_planned_followup, "after_temporary_fix": z.after_temporary_fix,
        "source_unknown": z.source_unknown, "chain_id": z.chain_id, "times_risen": z.times_risen,
        "skeptic_verdict": z.skeptic_verdict, "skeptic_notes": scrub_text(z.skeptic_notes) or "",
        "type_family": z.type_family, "department": z.department, "neighborhood": z.neighborhood,
        "district": z.district, "segment_id": z.segment_id, "coroner_label": z.coroner_label,
        "bulk_closure": z.bulk_closure, "close_year": z.close_year,
    }  # fmt: skip


def case_record(c: Case) -> dict:
    return {
        "id": c.id, "system": c.system, "open_time": c.open_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "close_time": c.close_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if c.close_utc else None,
        "type_raw": c.type_raw, "status": c.status or "", "closure_text": scrub_text(c.closure_text),
        "street": scrub_text(c.street), "lat": round(c.lat, 6), "lon": round(c.lon, 6),
    }  # fmt: skip


def _representative(z: Zombie, cases: Mapping[str, Case]) -> Case:
    return min((cases[m] for m in z.member_ids), key=lambda c: (c.open_utc, c.id))


def build_payloads(result: DetectionResult, cases: Mapping[str, Case], ctx: ExportContext) -> dict[str, Any]:
    """All payloads keyed by file path (relative to the output folder), unvalidated. `status.json` is not included."""
    dv = ctx.data_version
    zombies = sorted(result.zombies, key=lambda z: z.zombie_id)
    out: dict[str, Any] = {}
    out["zombies.json"] = {"data_version": dv, "zombies": [zombie_record(z) for z in zombies]}
    with_reports = {z.incident_id for z in zombies} | {f.incident_id for f in result.planned_followups}
    with_reports |= {s.incident_id for s in result.separate_deaths}
    out["incidents.json"] = {
        "data_version": dv,
        "incidents": [
            {
                "incident_id": i.incident_id, "member_ids": sorted(i.member_ids), "type_family": i.type_family,
                "department": i.department, "neighborhood": i.neighborhood, "district": i.district,
                "segment_id": i.segment_id, "close_time": i.close_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "coroner_label": i.coroner_label, "bulk_closure": i.bulk_closure,
            }
            for i in sorted(result.incidents, key=lambda i: i.incident_id)
            if i.incident_id in with_reports
        ],
    }  # fmt: skip
    reps = {z.zombie_id: _representative(z, cases) for z in zombies}
    out["points.json"] = {
        "data_version": dv, "n": len(zombies),
        "id": [z.zombie_id for z in zombies],
        "lat": [round(reps[z.zombie_id].lat, 6) for z in zombies],
        "lon": [round(reps[z.zombie_id].lon, 6) for z in zombies],
        "tier": [z.tier for z in zombies], "family": [z.type_family for z in zombies],
        "department": [z.department for z in zombies], "neighborhood": [z.neighborhood for z in zombies],
        "year": [z.close_year for z in zombies],
    }  # fmt: skip
    shards: dict[str, list[dict]] = defaultdict(list)
    for z in zombies:
        res = cases[z.resurrection_id]
        shards[f"{slug(z.neighborhood)}-{z.close_year}"].append(
            {
                "zombie_id": z.zombie_id, "original": case_record(reps[z.zombie_id]), "rereport": case_record(res),
                "cause_of_death": z.coroner_label, "gap_days": round(z.gap_days, 6),
                "resurrection_date": res.open_utc.strftime("%Y-%m-%d"), "confidence": round(z.confidence, 6),
                "tier": z.tier, "skeptic_verdict": z.skeptic_verdict,
                "skeptic_notes": scrub_text(z.skeptic_notes) or "", "reports_after": z.reports_after,
                "times_risen": z.times_risen, "bulk_closure": z.bulk_closure,
            }
        )  # fmt: skip
    for shard, cards in sorted(shards.items()):
        out[f"cards/{shard}.json"] = {"data_version": dv, "shard": shard, "cards": cards}
    out["exclusions.json"] = {
        "data_version": dv,
        "counts": dict(sorted(ctx.exclusion_counts.items())),
        "excluded_ids": {k: sorted(v)[:EXCLUDED_ID_CAP] for k, v in sorted(ctx.excluded_ids.items())},
        "excluded_pairs": dict(sorted(result.excluded_pairs.items())),
    }
    out["separate_deaths.json"] = {
        "data_version": dv,
        "separate_deaths": [
            {"incident_id": s.incident_id, "label": s.label, "rereport_id": s.rereport_id,
             "type_family": s.type_family, "department": s.department}
            for s in sorted(result.separate_deaths, key=lambda s: (s.incident_id, s.rereport_id))
        ],
    }  # fmt: skip
    by_inc = {i.incident_id: i for i in result.incidents}
    offenders = []
    for c in sorted(result.repeat_offenders, key=lambda c: c.chain_id):
        first = by_inc[c.chain_id]
        rep = min((cases[m] for m in first.member_ids), key=lambda x: (x.open_utc, x.id))
        offenders.append(
            {
                "chain_id": c.chain_id, "times_risen": c.times_risen, "headline_count": c.headline_count,
                "incident_ids": sorted(c.incident_ids), "lat": round(rep.lat, 6), "lon": round(rep.lon, 6),
                "block_level": False, "type_family": first.type_family, "neighborhood": first.neighborhood,
            }
        )  # fmt: skip
    out["repeat_offenders.json"] = {"data_version": dv, "repeat_offenders": offenders}
    out["bulk_closures.json"] = {"data_version": dv, "bulk_closures": ctx.bulk_closures}
    return out


def build_status(result: DetectionResult, ctx: ExportContext) -> dict:
    stats = dict(ctx.stats_status or {})
    status: dict[str, Any] = {
        "data_version": ctx.data_version, "last_run": ctx.run_time, "ok": not ctx.anomalies,
        "row_counts": dict(sorted(ctx.row_counts.items())), "anomalies": sorted(ctx.anomalies),
        "segments": ctx.segments, "calibration_warning": stats.get("calibration_warning"),
        "headline_count": result.headline_count, "source_unknown_count": result.count("source_unknown"),
        "sensitivity_count": result.count("sensitivity"),
    }  # fmt: skip
    if ctx.data_end:
        status["data_end"] = ctx.data_end
    return status


def export_all(result: DetectionResult, cases: Mapping[str, Case], out_dir: Path, ctx: ExportContext) -> list[Path]:
    """Validate everything, then write every file, then `status.json` last (REQ-EXP-1.1-1.3). Returns the paths."""
    payloads = build_payloads(result, cases, ctx)
    status = build_status(result, ctx)
    for name, payload in payloads.items():
        validate("card" if name.startswith("cards/") else name.removesuffix(".json"), payload)
    validate("status", status)
    out_dir = Path(out_dir)
    written = []
    for name in sorted(payloads):
        write_text_atomic(out_dir / name, canonical_json(payloads[name]))
        written.append(out_dir / name)
    write_text_atomic(out_dir / "status.json", canonical_json(status))
    written.append(out_dir / "status.json")
    return written


def write_duckdb_atomic(final: Path, build: Callable[[duckdb.DuckDBPyConnection], None]) -> Path:
    """Build the DuckDB file under a temporary name, then rename it, so a reader never sees a half-written file."""
    final = Path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")
    for stale in (tmp, tmp.with_name(tmp.name + ".wal")):
        stale.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        build(con)
        con.execute("checkpoint")
    except BaseException:
        con.close()
        tmp.unlink(missing_ok=True)
        raise
    con.close()
    os.replace(tmp, final)
    return final
