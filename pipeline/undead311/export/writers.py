"""Schema-validated, deterministic exports (REQ-EXP-1, REQ-ING-PII).

Every payload is validated against `schemas/<name>.schema.json` BEFORE anything is written; one invalid record refuses the
whole export (REQ-EXP-1.1). JSON is written with sorted keys and sorted records, so the same input gives byte-identical
files (REQ-EXP-1.3). Each file is written to a temporary name and renamed. `status.json` is written last (REQ-EXP-1.1),
so a failed run never leaves a status that claims success. Free text goes through the PII scrub (REQ-ING-PII.1).
`write_duckdb_atomic` builds the DuckDB file beside the target and renames it (REQ-EXP-1.4).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb
from jsonschema import Draft202012Validator

from undead311.detect.model import Case, DetectionResult, Zombie
from undead311.detect.params import DEFAULT, Params
from undead311.duck import connect
from undead311.export.notes import note_counts, shown_note
from undead311.export.privacy import (
    SegmentInfo,
    block_level_locations,
    block_location_by_case,
    colocated_block_locations,
)
from undead311.ingest.pii import scrub_text
from undead311.paths import repo_root

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"
EXCLUDED_ID_CAP = 5000
# REQ-EXP-SIZE.1: the files the first view loads (status, map points, the two-number scorecard, the judge tour), by path
# relative to the output folder. Their total, before compression, must stay under the budget.
FIRST_VIEW_FILES = ("status.json", "points.json", "stats/scorecard.json", "stats/judge_tour.json")
# REQ-EXP-SIZE.2: the 3 MB budget is the gzip transfer size of the first-view files (what a phone downloads), taken as
# 3,000,000 bytes so the check is not generous. A single first-view file may not exceed the raw ceiling either, because the
# browser parses it uncompressed. REQ-EXP-SIZE.3: no file the site loads is over FILE_BUDGET_GZIP_BYTES compressed.
FIRST_VIEW_BUDGET_BYTES = 3_000_000
FIRST_VIEW_RAW_CEILING_BYTES = 8_000_000
FILE_BUDGET_GZIP_BYTES = 2_000_000
GZIP_LEVEL = 6  # the level hosts such as Netlify use for on-the-fly gzip; mtime 0 keeps the size deterministic
HEADLINE_TIER = "headline"
OTHER_TIERS = ("source_unknown", "city_rereport", "sensitivity")  # loaded on demand: points/<tier>.json


class ContractError(ValueError):
    """A payload does not validate against its JSON Schema (REQ-EXP-1.1)."""


class PayloadBudgetExceeded(RuntimeError):
    """The first-view files are larger than FIRST_VIEW_BUDGET_BYTES (REQ-EXP-SIZE.2)."""


def gzip_size(data: bytes) -> int:
    """Transfer size of `data` under gzip (REQ-EXP-SIZE.2): deterministic, so a rerun reports the same number."""
    return len(gzip.compress(data, GZIP_LEVEL, mtime=0))


def first_view_bytes(sizes: Mapping[str, int]) -> int:
    """Total size of the first-view files present in `sizes` (name relative to the output folder -> bytes). Pass gzip sizes
    for the budget (REQ-EXP-SIZE.2) or raw sizes for a report."""
    return sum(n for name, n in sizes.items() if name in FIRST_VIEW_FILES)


def check_first_view_budget(sizes: Mapping[str, int], budget: int = FIRST_VIEW_BUDGET_BYTES) -> int:
    """Raise PayloadBudgetExceeded when the first-view files exceed `budget` bytes (gzip sizes, REQ-EXP-SIZE.2); return the total."""
    total = first_view_bytes(sizes)
    if total > budget:
        parts = ", ".join(f"{n} {sizes[n]:,} B" for n in FIRST_VIEW_FILES if n in sizes)
        raise PayloadBudgetExceeded(f"first-view files total {total:,} B gzip, over the {budget:,} B budget ({parts})")
    return total


def check_raw_ceiling(raw_sizes: Mapping[str, int], ceiling: int = FIRST_VIEW_RAW_CEILING_BYTES) -> None:
    """No single first-view file may be over `ceiling` bytes uncompressed (REQ-EXP-SIZE.2)."""
    big = {n: raw_sizes[n] for n in FIRST_VIEW_FILES if raw_sizes.get(n, 0) > ceiling}
    if big:
        raise PayloadBudgetExceeded(
            "first-view file over the raw ceiling of " + f"{ceiling:,} B: " + ", ".join(f"{n} {v:,} B" for n, v in sorted(big.items()))
        )


def check_file_budget(gz_sizes: Mapping[str, int], budget: int = FILE_BUDGET_GZIP_BYTES) -> None:
    """No file the site loads may be over `budget` bytes compressed (REQ-EXP-SIZE.3): shard a file that is."""
    big = {n: v for n, v in gz_sizes.items() if v > budget}
    if big:
        raise PayloadBudgetExceeded(
            f"files over the {budget:,} B gzip budget: " + ", ".join(f"{n} {v:,} B" for n, v in sorted(big.items()))
        )


def schema_name(path: str) -> str:
    """The JSON Schema that validates an exported file (REQ-EXP-1.1)."""
    if path.startswith("cards/"):
        return "card"
    if path in ("zombies/index.json", "incidents/index.json"):
        return "shard_index"
    if path.startswith("zombies/"):
        return "zombies"
    if path.startswith("incidents/"):
        return "incidents"
    if path.startswith("points/"):
        return "points"
    return path.removesuffix(".json")


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
    city_origin: Mapping[str, Any] | None = None
    dataset: str | None = None  # "sample" or "full" (REQ-STAT-EXP.1)
    # Dry-run override (owner decision 2026-11-16, option D): an over-budget first view is written with an anomaly instead of
    # failing. Only `run_full.py --dry-run-over-budget` sets it; `make pipeline`, the nightly and judging runs never do.
    allow_over_budget: bool = False
    #: raw and gzip size of every file of the export, set by export_all (REQ-EXP-SIZE.2)
    sizes: dict[str, dict[str, int]] = field(default_factory=dict)
    #: SAM segment ID -> midpoint and class, for block-level repeat offenders (REQ-EXP-PRIV.1); None without the SAM file
    segment_info: Mapping[str, SegmentInfo] | None = None
    ok: bool = True


def zombie_record(z: Zombie) -> dict:
    return {
        "zombie_id": z.zombie_id, "incident_id": z.incident_id, "resurrection_id": z.resurrection_id,
        "reports_after": z.reports_after, "gap_days": round(z.gap_days, 6), "match_mode": z.match_mode,
        "distance_m": round(z.distance_m, 3), "tier": z.tier, "baseline_p": z.baseline_p,
        "confidence": round(z.confidence, 6), "confidence_partial": z.confidence_partial,
        "is_planned_followup": z.is_planned_followup, "after_temporary_fix": z.after_temporary_fix,
        "source_unknown": z.source_unknown, "city_rereport": z.city_rereport, "chain_id": z.chain_id, "times_risen": z.times_risen,
        "skeptic_verdict": z.skeptic_verdict, "skeptic_notes": scrub_text(z.skeptic_notes) or "",
        "type_family": z.type_family, "department": z.department, "neighborhood": z.neighborhood,
        "district": z.district, "segment_id": z.segment_id, "coroner_label": z.coroner_label,
        "bulk_closure": z.bulk_closure, "close_year": z.close_year, "resurrection_date": z.resurrection_date,
    }  # fmt: skip


def case_record(
    c: Case, block: tuple[float, float] | None = None, notes: Mapping[str, int] | None = None
) -> dict:
    """One case's card fields. `block` is the (lat, lon) of a block-level repeat-offender chain: the case then carries that
    location and no street text, so the exact address is not exported (REQ-EXP-PRIV.1, ops#167). `notes` counts the closed
    cases per scrubbed closure note: a note shared by fewer than 5 cases is not exported, and the record says so with
    `closure_text_hidden` (REQ-ING-PII.5). Without counts, no note is exported."""
    lat, lon = block if block is not None else (c.lat, c.lon)
    text, hidden = shown_note(c.closure_text, notes or {})
    rec = {
        "id": c.id, "system": c.system, "open_time": c.open_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "close_time": c.close_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if c.close_utc else None,
        "type_raw": c.type_raw, "status": c.status or "", "closure_text": text,
        "street": None if block is not None else scrub_text(c.street), "lat": round(lat, 6), "lon": round(lon, 6),
    }  # fmt: skip
    if hidden:
        rec["closure_text_hidden"] = True
    return rec


def closing_member(z: Zombie, cases: Mapping[str, Case]) -> Case:
    """The latest-closing member, ties by smallest ID: the closure that ended the incident (ZD step 2). It is the source of
    the Coroner label and of `gap_days`, so the card's `original` shows this case (REQ-EXP-1.1)."""
    return min((cases[m] for m in z.member_ids), key=lambda c: (-c.close_utc.timestamp(), c.id))  # type: ignore[union-attr]


def exported_case_ids(z: Zombie, cases: Mapping[str, Case]) -> tuple[str, str]:
    """IDs of the two cases whose free text a zombie's card exports: the closing member (the card's original) and the
    re-report. The run report's PII counts cover exactly these (REQ-ING-PII.3, ops#40)."""
    return closing_member(z, cases).id, z.resurrection_id


def shard_index(dv: str, kind: str, shards: Mapping[str, tuple[tuple[str | None, int, set[str]], int, dict | None]]) -> dict:
    """The index of a sharded file set (REQ-EXP-SIZE.3): each shard's neighborhood, year, size, districts and tier counts."""
    rows = []
    for key in sorted(shards):
        (neighborhood, year, districts), n, tiers = shards[key]
        row: dict[str, Any] = {"shard": key, "neighborhood": neighborhood, "year": year, "n": n, "districts": sorted(districts)}
        if tiers is not None:
            row["tiers"] = dict(sorted(tiers.items()))
        rows.append(row)
    return {"data_version": dv, "kind": kind, "shards": rows}


def district_summaries(zombies: list[Zombie]) -> list[dict]:
    """Headline possible zombies per council district, by family and by year (REQ-EXP-SIZE.3): what the district report cards
    show, so a page needs no zombie shard. A zombie with no district is left out, never guessed."""
    by: dict[str, list[Zombie]] = defaultdict(list)
    for z in zombies:
        if z.tier == HEADLINE_TIER and z.district:
            by[z.district].append(z)

    def num_key(d: str) -> tuple[float, str]:
        return (float(d), d) if re.fullmatch(r"\d+(\.\d+)?", d) else (float("inf"), d)

    out = []
    for district in sorted(by, key=num_key):
        zs = by[district]
        fam: dict[str, int] = defaultdict(int)
        yr: dict[int, int] = defaultdict(int)
        for z in zs:
            fam[z.type_family] += 1
            yr[int(z.resurrection_date[:4])] += 1
        out.append({
            "district": district, "count": len(zs),
            "by_family": [{"family": f, "count": n} for f, n in sorted(fam.items(), key=lambda kv: (-kv[1], kv[0]))],
            "by_year": [{"year": y, "count": n} for y, n in sorted(yr.items())],
        })  # fmt: skip
    return out


def build_payloads(result: DetectionResult, cases: Mapping[str, Case], ctx: ExportContext) -> dict[str, Any]:
    """All payloads keyed by file path (relative to the output folder), unvalidated. `status.json` is not included."""
    dv = ctx.data_version
    zombies = sorted(result.zombies, key=lambda z: z.zombie_id)
    out: dict[str, Any] = {}
    notes = note_counts(c.closure_text for c in cases.values() if c.close_utc is not None)  # REQ-ING-PII.5
    with_reports = {z.incident_id for z in zombies} | {f.incident_id for f in result.planned_followups}
    with_reports |= {s.incident_id for s in result.separate_deaths}
    inc_shards: dict[str, list[dict]] = defaultdict(list)
    inc_meta: dict[str, tuple[str | None, int, set[str]]] = {}
    for i in sorted(result.incidents, key=lambda i: i.incident_id):
        if i.incident_id not in with_reports:
            continue
        key = f"{slug(i.neighborhood)}-{i.close_utc.year}"
        inc_shards[key].append(
            {
                "incident_id": i.incident_id, "member_ids": sorted(i.member_ids), "type_family": i.type_family,
                "department": i.department, "neighborhood": i.neighborhood, "district": i.district,
                "segment_id": i.segment_id, "close_time": i.close_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "coroner_label": i.coroner_label, "bulk_closure": i.bulk_closure,
            }
        )  # fmt: skip
        _nb, _yr, ds = inc_meta.setdefault(key, (i.neighborhood, i.close_utc.year, set()))
        if i.district:
            ds.add(i.district)
    for key, rows in sorted(inc_shards.items()):
        out[f"incidents/{key}.json"] = {"data_version": dv, "shard": key, "incidents": rows}
    out["incidents/index.json"] = shard_index(dv, "incidents", {k: (inc_meta[k], len(v), None) for k, v in inc_shards.items()})
    # block-level repeat-offender chains: every row that touches the chain's cases carries the block location (REQ-EXP-PRIV.1, ops#167)
    locations = block_level_locations(result, cases, ctx.segment_info)
    block_of = block_location_by_case(result, locations)  # every case that touches a block-level chain (ops#180)
    block_of = {**colocated_block_locations(result, cases, block_of), **block_of}  # a zombie at the same spot (ops#185)

    def blk(z: Zombie) -> tuple[float, float] | None:
        return block_of.get(z.resurrection_id)

    reps = {z.zombie_id: closing_member(z, cases) for z in zombies}  # the card's original (ops#40)
    spot = {z.zombie_id: blk(z) or (reps[z.zombie_id].lat, reps[z.zombie_id].lon) for z in zombies}
    def points_for(zs: list[Zombie]) -> dict:
        return {
            "data_version": dv, "n": len(zs),
            "id": [z.zombie_id for z in zs],
            "lat": [round(spot[z.zombie_id][0], 6) for z in zs],
            "lon": [round(spot[z.zombie_id][1], 6) for z in zs],
            "tier": [z.tier for z in zs], "family": [z.type_family for z in zs],
            "department": [z.department for z in zs], "neighborhood": [z.neighborhood for z in zs],
            "year": [int(z.resurrection_date[:4]) for z in zs],
            "date": [z.resurrection_date for z in zs],  # the day of the re-report: the time-lapse needs no zombie shard
        }  # fmt: skip

    # REQ-EXP-SIZE.4: the first view loads the headline tier only; every other tier is its own file, loaded when switched on
    out["points.json"] = points_for([z for z in zombies if z.tier == HEADLINE_TIER])
    for tier in OTHER_TIERS:
        out[f"points/{tier}.json"] = points_for([z for z in zombies if z.tier == tier])
    shards: dict[str, list[dict]] = defaultdict(list)
    zshards: dict[str, list[dict]] = defaultdict(list)
    zmeta: dict[str, tuple[str | None, int, set[str]]] = {}
    ztiers: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for z in zombies:
        res = cases[z.resurrection_id]
        zkey = f"{slug(z.neighborhood)}-{z.resurrection_date[:4]}"
        zshards[zkey].append(zombie_record(z))
        _nb, _yr, ds = zmeta.setdefault(zkey, (z.neighborhood, int(z.resurrection_date[:4]), set()))
        if z.district:
            ds.add(z.district)
        ztiers[zkey][z.tier] += 1
        shards[zkey].append(
            {
                "zombie_id": z.zombie_id, "original": case_record(closing_member(z, cases), blk(z), notes),
                "rereport": case_record(res, blk(z), notes),
                "cause_of_death": z.coroner_label, "gap_days": round(z.gap_days, 6),
                "resurrection_date": z.resurrection_date, "confidence": round(z.confidence, 6),
                "confidence_partial": z.confidence_partial,
                "tier": z.tier, "skeptic_verdict": z.skeptic_verdict,
                "skeptic_notes": scrub_text(z.skeptic_notes) or "", "reports_after": z.reports_after,
                "times_risen": z.times_risen, "bulk_closure": z.bulk_closure,
            }
        )  # fmt: skip
    for shard, cards in sorted(shards.items()):
        out[f"cards/{shard}.json"] = {"data_version": dv, "shard": shard, "cards": cards}
    for shard, rows in sorted(zshards.items()):
        out[f"zombies/{shard}.json"] = {"data_version": dv, "shard": shard, "zombies": rows}
    out["zombies/index.json"] = shard_index(dv, "zombies", {k: (zmeta[k], len(v), dict(ztiers[k])) for k, v in zshards.items()})
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
    first_of: dict[str, str] = {}  # chain -> its earliest headline zombie (by re-report date, then ID), to open its first card
    for z in sorted((z for z in zombies if z.tier == HEADLINE_TIER), key=lambda z: (z.resurrection_date, z.zombie_id)):
        first_of.setdefault(z.chain_id, z.zombie_id)
    offenders = []
    for c in sorted(result.repeat_offenders, key=lambda c: c.chain_id):
        first = by_inc[c.chain_id]
        lat, lon, block = locations[c.chain_id]
        offenders.append(
            {
                "chain_id": c.chain_id, "times_risen": c.times_risen, "headline_count": c.headline_count,
                "incident_ids": sorted(c.incident_ids), "lat": round(lat, 6), "lon": round(lon, 6),
                "block_level": block, "type_family": first.type_family, "neighborhood": first.neighborhood,
                "first_zombie_id": first_of.get(c.chain_id),
            }
        )  # fmt: skip
    out["repeat_offenders.json"] = {"data_version": dv, "repeat_offenders": offenders}
    out["bulk_closures.json"] = {"data_version": dv, "bulk_closures": ctx.bulk_closures}
    out["districts.json"] = {"data_version": dv, "districts": district_summaries(zombies)}
    return out


def build_status(result: DetectionResult, ctx: ExportContext) -> dict:
    stats = dict(ctx.stats_status or {})
    status: dict[str, Any] = {
        "data_version": ctx.data_version, "last_run": ctx.run_time, "ok": ctx.ok,
        "row_counts": dict(sorted(ctx.row_counts.items())), "anomalies": sorted(ctx.anomalies),
        "segments": ctx.segments, "calibration_warning": stats.get("calibration_warning"),
        "headline_count": result.headline_count, "source_unknown_count": result.count("source_unknown"),
        "city_rereport_count": result.count("city_rereport"), "mirror_copies_merged": len(result.mirror_ids),
        "sensitivity_count": result.count("sensitivity"),
    }  # fmt: skip
    status["planned_followup_count"] = len(result.planned_followups)
    if ctx.city_origin:
        status["city_rereport_under_1h_count"] = int(ctx.city_origin["city_rereport_under_1h"])
    if ctx.dataset:
        status["dataset"] = ctx.dataset
    if ctx.data_end:
        status["data_end"] = ctx.data_end
    return status


def export_all(result: DetectionResult, cases: Mapping[str, Case], out_dir: Path, ctx: ExportContext) -> list[Path]:
    """Validate everything, then write every file, then `status.json` last (REQ-EXP-1.1-1.3). Returns the paths."""
    payloads = build_payloads(result, cases, ctx)
    status = build_status(result, ctx)
    for name, payload in payloads.items():
        validate(schema_name(name), payload)
    validate("status", status)
    out_dir = Path(out_dir)
    texts = {name: canonical_json(payloads[name]) for name in sorted(payloads)}
    texts["status.json"] = canonical_json(status)
    blobs = {name: t.encode("utf-8") for name, t in texts.items()}
    sizes = {name: len(b) for name, b in blobs.items()}
    gz = {name: gzip_size(b) for name, b in blobs.items()}
    stats_dir = out_dir / "stats"
    if stats_dir.is_dir():  # stats files are written before the export; their size counts too (REQ-EXP-SIZE.2-3)
        for f in sorted(stats_dir.glob("*.json")):
            name = f"stats/{f.name}"
            if name not in sizes:
                data = f.read_bytes()
                sizes[name], gz[name] = len(data), gzip_size(data)
    ctx.sizes = {"raw": dict(sizes), "gzip": dict(gz)}
    try:
        check_first_view_budget(gz)  # before anything is written: an over-budget run leaves the old files in place
        check_raw_ceiling(sizes)
        check_file_budget(gz)
    except PayloadBudgetExceeded as exc:
        if not ctx.allow_over_budget:
            raise
        ctx.anomalies.append(f"DRY RUN ONLY, over the first-view budget: {exc}")
        texts["status.json"] = canonical_json(build_status(result, ctx))
    written = []
    for name in sorted(texts):
        if name == "status.json":
            continue
        write_text_atomic(out_dir / name, texts[name])
        written.append(out_dir / name)
    if (out_dir / "stats").is_dir():
        written += sorted((out_dir / "stats").glob("*.json"))
    status_path = out_dir / "status.json"
    write_text_atomic(status_path, texts["status.json"])  # the last file written (REQ-EXP-1.1)
    written.append(status_path)
    return written


STAGING_MAX_AGE_S = 24 * 3600  # where a process start time can't be read, a folder this old is stale whatever its pid


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # the process exists, owned by someone else
    return True


def _proc_start(pid: int) -> str | None:
    """The process start time in clock ticks since boot (field 22 of /proc/<pid>/stat), or None where /proc is absent.
    A reused pid has a different start time, so pid plus start time names one process for good."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat.rpartition(")")[2].split()[19]  # fields after the command name; starttime is the 22nd overall


def _owner_alive(folder: Path) -> bool:
    """True when the process that made `folder` is still running (ops#93). The folder name ends in `-<pid>-<start>`,
    the writer's pid and start time: a pid that was reused by another process has a different start time, so it does
    not keep a dead run's folder. A name with no start time (or no /proc to read one) trusts the pid only while the
    folder is under STAGING_MAX_AGE_S old."""
    parts = folder.name.rsplit(".staging-", 1)[-1].split("-")
    if not parts[0].isdigit() or int(parts[0]) == os.getpid() or not _pid_alive(int(parts[0])):
        return False
    now = _proc_start(int(parts[0]))
    if now is None or len(parts) < 2 or not parts[1]:
        try:
            return time.time() - folder.stat().st_mtime < STAGING_MAX_AGE_S
        except OSError:
            return False
    return now == parts[1]


def remove_stale_staging(target: Path) -> list[Path]:
    """Delete `.<name>.staging-<pid>` folders beside `target` left by a killed run (REQ-ING-NIGHTLY.1, ops#85, ops#93).

    A SIGKILL or CI timeout skips the `finally` cleanup, and later runs have a new pid, so the folder would stay (under
    web/public it would ship with the static build). A folder is kept only while the exact process that made it runs
    (pid plus start time in its name); a reused pid does not keep a dead run's folder."""
    target = Path(target)
    removed = []
    for old in sorted(target.parent.glob(f".{target.name}.staging-*")):
        if old.is_dir() and not _owner_alive(old):
            shutil.rmtree(old, ignore_errors=True)
            removed.append(old)
    return removed


def find_staging_leftovers(root: Path) -> list[Path]:
    """Every `.*.staging-*` folder under `root`: nothing of the kind may ship in a build (ops#93)."""
    return sorted(p for p in Path(root).rglob(".*.staging-*") if p.is_dir()) if Path(root).is_dir() else []


def staging_dir(target: Path) -> Path:
    """A fresh hidden folder beside `target` (same filesystem, so `os.replace` is atomic) for one run's output."""
    target = Path(target)
    remove_stale_staging(target)
    stage = target.parent / f".{target.name}.staging-{os.getpid()}-{_proc_start(os.getpid()) or ''}"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    return stage


class Swap:
    """Move every file under `stage` into `target` after a successful run (REQ-ING-NIGHTLY.1), with rollback.

    `apply()` replaces each file atomically (`last` goes last, so the site never sees
    a status newer than its data) and removes files in `target` for which `owned(relative path)` is true but that this run
    did not produce (a stale card shard, a stats file the run no longer writes). Files that are not owned are never touched.
    Every file it replaces or removes is first moved to `stage/.backup`, so `rollback()` (also called when `apply()` itself
    fails part-way) puts `target` back exactly as it was. Nothing happens to `target` before `apply()`."""

    def __init__(self, stage: Path, target: Path, owned: Callable[[str], bool] = lambda rel: False, last: str = "status.json"):
        self.stage, self.target, self.owned, self.last = Path(stage), Path(target), owned, last
        self.backup = self.stage / ".backup"
        self.paths: list[Path] = []
        self._undo: list[tuple[Path, Path | None]] = []  # (target file, its backup or None when it did not exist)

    def _plan(self) -> tuple[list[str], list[str]]:
        staged = sorted(
            p.relative_to(self.stage).as_posix()
            for p in self.stage.rglob("*")
            if p.is_file() and p.suffix != ".tmp" and ".backup" not in p.relative_to(self.stage).parts
        )
        order = [r for r in staged if r != self.last]
        order += [r for r in (self.last,) if r in staged]
        stale = []
        if self.target.is_dir():
            produced = set(staged)
            for f in sorted(p for p in self.target.rglob("*") if p.is_file()):
                rel = f.relative_to(self.target).as_posix()
                if rel not in produced and self.owned(rel):
                    stale.append(rel)
        return order, stale

    def _save(self, rel: str) -> None:
        dest = self.target / rel
        if dest.is_file():
            saved = self.backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            os.replace(dest, saved)
            self._undo.append((dest, saved))
        else:
            self._undo.append((dest, None))

    def apply(self) -> Swap:
        order, stale = self._plan()
        tail = [r for r in order if r == self.last]
        body = [r for r in order if r not in tail]
        try:
            for rel in body:
                self._move_in(rel)
            for rel in stale:  # a stale file goes before the status file, which therefore still ends the swap
                self._save(rel)
            for rel in tail:
                self._move_in(rel)
        except BaseException:
            self.rollback()
            raise
        self.paths = [self.target / rel for rel in order]
        return self

    def _move_in(self, rel: str) -> None:
        self._save(rel)
        dest = self.target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.stage / rel, dest)

    def rollback(self) -> None:
        """Restore `target` to its state before `apply()`."""
        for dest, saved in reversed(self._undo):
            if saved is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(saved, dest)
            else:
                dest.unlink(missing_ok=True)
        self._undo.clear()
        self.paths = []


def swap_into(
    stage: Path, target: Path, owned: Callable[[str], bool] = lambda rel: False, last: str = "status.json"
) -> list[Path]:
    """`Swap(...).apply().paths`: the final paths of the files moved into `target`."""
    return Swap(stage, target, owned, last).apply().paths


def write_duckdb_atomic(
    final: Path,
    build: Callable[[duckdb.DuckDBPyConnection], None],
    commit: Callable[[], None] | None = None,
    rollback: Callable[[], None] | None = None,
    keep_partial: bool = False,
) -> Path:
    """Build the DuckDB file under a temporary name, then rename it, so a reader never sees a half-written file.

    `keep_partial` (a resumable run, REQ-OPS-RUN.2) opens the temporary file as it is instead of deleting it first, and keeps
    it when the build, the commit or the rename fails, so a restart can continue from the stages already committed in it.

    `commit` runs after a successful build and before the rename (the pipeline swaps its output files in there). If it or
    the rename fails, `rollback` runs, the temporary file is removed and the error is raised: the previous DuckDB file
    stays in place (REQ-EXP-1.4, REQ-ING-NIGHTLY.1)."""
    final = Path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")
    if not keep_partial:
        for stale in (tmp, tmp.with_name(tmp.name + ".wal")):
            stale.unlink(missing_ok=True)
    con = connect(tmp)  # REQ-OPS-DUCK.3
    try:
        build(con)
        con.execute("checkpoint")
    except BaseException:
        con.close()
        if not keep_partial:
            tmp.unlink(missing_ok=True)
        raise
    con.close()
    try:
        if commit is not None:
            commit()
        os.replace(tmp, final)
    except BaseException:
        if rollback is not None:
            rollback()
        if not keep_partial:
            tmp.unlink(missing_ok=True)
        raise
    return final
