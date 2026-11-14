"""Pipeline orchestration (REQ-ING-1, REQ-ING-NIGHTLY, REQ-ING-SAMPLE.1).

`run_pipeline` runs: load -> normalize -> crosswalk -> clean -> Coroner join -> detect -> (stats, when present) -> export.
The sample run (`sample=True`) reads `data/sample/sample_311.csv` (already crosswalked, core scope) into the same
`cases_clean` table and then takes the same Coroner, detect and export path, with no network and no raw data.
The DuckDB file is built under a temporary name and renamed on success (REQ-EXP-1.4). A run report records row counts,
exclusions, excluded pairs, label coverage, PII counts and file sizes (also written to `run_report.json`).
"""

from __future__ import annotations

import importlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from undead311.coroner.join import JoinReport, join_labels
from undead311.coroner.templates import build_templates
from undead311.detect.cases import cases_from_table
from undead311.detect.core import city_origin_summary, detect
from undead311.detect.edges import sql_edges
from undead311.detect.model import DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.detect.skeptic import build_input, join_objections, write_input
from undead311.export.writers import (
    ExportContext,
    canonical_json,
    data_version,
    export_all,
    exported_case_ids,
    snapshot_date,
    write_duckdb_atomic,
    write_text_atomic,
)
from undead311.ingest.clean import REASONS, clean, ids_by_reason
from undead311.ingest.crosswalk import apply_crosswalk
from undead311.ingest.load import load
from undead311.ingest.normalize import normalize
from undead311.ingest.pii import PiiCounter
from undead311.ingest.quality import on_time_anomalies, on_time_coverage
from undead311.paths import data_dir, worktree_root

STATS_ABSENT_NAMES = ("undead311.stats", "undead311.stats.pipeline")  # the only ModuleNotFoundError names that mean "absent"
STATS_STALE_FILES = ("scorecard.json", "judge_tour.json", "stats_status.json")
CITY_SHARE_WARN = 0.5  # run-report anomaly when this share of headline resurrections is city-originated (ops#29)


@dataclass
class RunReport:
    sample: bool
    ok: bool = True
    data_version: str = ""
    row_counts: dict[str, int] = field(default_factory=dict)
    exclusions: dict[str, int] = field(default_factory=dict)
    excluded_pairs: dict[str, int] = field(default_factory=dict)
    normalization_issues: dict[str, int] = field(default_factory=dict)
    candidate_placeholders: list[dict] = field(default_factory=list)
    label_coverage: float = 1.0
    unlabeled: int = 0
    pii_counts: dict[str, int] = field(default_factory=dict)
    tier_counts: dict[str, int] = field(default_factory=dict)
    city_origin: dict[str, float | int] = field(default_factory=dict)
    planned_followups: int = 0
    file_sizes: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    stats: str = "not present"
    seconds: float = 0.0

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    def summary(self) -> str:
        t = self.tier_counts
        co = self.city_origin
        lines = [
            f"undead311 pipeline ({'sample' if self.sample else 'full'}) {'ok' if self.ok else 'FAILED'} in {self.seconds:.1f}s",
            f"  data_version: {self.data_version}",
            f"  rows: {self.row_counts}",
            f"  exclusions: {self.exclusions}",
            f"  excluded pairs: {self.excluded_pairs}",
            f"  Coroner label coverage: {self.label_coverage:.1%} ({self.unlabeled} unlabeled)",
            "  zombies: " + ", ".join(f"{k} {t.get(k, 0)}" for k in ("headline", "source_unknown", "sensitivity")),
            (
                f"  city-originated headline resurrections: {co.get('city_originated', 0)} of {co.get('headline', 0)} "
                f"({co.get('city_originated_share', 0.0):.1%}), {co.get('city_originated_under_1h', 0)} opened under "
                f"1 h after closure; planned follow-ups kept out: {self.planned_followups}"
            ),
            f"  PII replacements: {self.pii_counts}",
            f"  stats: {self.stats}",
            f"  files: {len(self.file_sizes)}, {sum(self.file_sizes.values()):,} bytes",
        ]
        lines += [f"  warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def _zombie_ids(path: Path, key: str = "zombie_ids") -> list[str]:
    if not path.is_file():
        return []
    try:
        return [str(x) for x in json.loads(path.read_text()).get(key, [])]
    except (ValueError, AttributeError):
        return []


def _validation_ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    import csv

    with path.open(newline="") as f:
        return [r["zombie_id"] for r in csv.DictReader(f) if r.get("zombie_id")]


def _load_sample(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    con.execute("create table sample_raw as select * from read_csv(?, all_varchar=true, header=true)", [str(csv_path)])
    con.execute("""
        create table cases_clean as
        select id, system, try_cast(open_time_utc as timestamp) as open_time_utc,
               try_cast(close_time_utc as timestamp) as close_time_utc, status, closure_text,
               nullif(closure_code, '') as closure_code, type_raw, type_family, scope_tier,
               lower(city_originated_type) = 'true' as city_originated_type, false as catch_all,
               case on_time when 'true' then true when 'false' then false end as on_time,
               predecessor_ids, nullif(department, '') as department, nullif(neighborhood, '') as neighborhood,
               NULL::varchar as district, nullif(street, '') as street, try_cast(lat as double) as lat,
               try_cast(lon as double) as lon, nullif(source, '') as source, NULL::varchar as segment_id,
               NULL::double as segment_snap_m, NULL::varchar as coroner_label
        from sample_raw order by id, system
    """)
    con.execute("update cases_clean set catch_all = predecessor_ids <> '' and system = 'new' and type_raw = 'Street Light Other'")
    return con.execute("select count(*) from cases_clean").fetchone()[0]


def run_pipeline(
    sample: bool = False,
    out_dir: str | Path | None = None,
    p: Params = DEFAULT,
    run_time: str | None = None,
    raw_dir: Path | None = None,
    work_dir: Path | None = None,
    snapshot_md: Path | None = None,
) -> RunReport:
    """Run every stage and export. Raises on a stage failure; previous outputs stay in place (DuckDB: atomic)."""
    t0 = time.time()
    root = worktree_root()
    base = work_dir or data_dir()
    processed = base / ("processed-sample" if sample else "processed")
    out = Path(out_dir) if out_dir else root / "web" / "public" / "data"
    report = RunReport(sample=sample)
    dataset = "sample" if sample else "full"  # REQ-STAT-EXP.1 (ops#51)
    snap = snapshot_date(root / "data" / "SNAPSHOT.md")
    version = data_version(snap, p, root)
    report.data_version = version
    labels_csv = root / "data" / "labels" / "coroner_labels.csv"
    pii = PiiCounter()
    state: dict = {}

    def build(con: duckdb.DuckDBPyConnection) -> None:
        excluded: dict[str, list[str]] = {r: [] for r in REASONS}
        if sample:
            report.row_counts["sample_rows"] = _load_sample(con, root / "data" / "sample" / "sample_311.csv")
            report.exclusions = dict.fromkeys(REASONS, 0)
        else:
            lr = load(con, raw_dir or base / "raw", snapshot_md or root / "data" / "SNAPSHOT.md")
            report.row_counts.update(raw_legacy=lr.legacy_rows, raw_new=lr.new_rows)
            nr = normalize(con)
            report.row_counts["cases_norm"] = nr.rows
            report.normalization_issues = nr.issues
            apply_crosswalk(con)
            cr = clean(con)
            report.exclusions = cr.counts
            report.candidate_placeholders = cr.candidate_placeholders
            report.row_counts["cases_clean"] = cr.kept
            excluded = ids_by_reason(con)
        build_templates(con, processed)
        jr: JoinReport = join_labels(con, labels_csv)
        report.label_coverage, report.unlabeled = jr.covered_share, jr.unlabeled
        if jr.labels_file_missing:
            report.warnings.append("data/labels/coroner_labels.csv is missing: every closure is labeled `other`")
        report.warnings += on_time_anomalies(on_time_coverage(con))  # REQ-STAT-SF.1 (ops#49)
        cases = cases_from_table(con, "cases_clean")
        report.row_counts["in_scope_cases"] = len(cases)
        edges = sql_edges(con, cases, p)
        report.row_counts["edges"] = len(edges)
        result: DetectionResult = detect(cases, p, edges)
        by_id = {c.id: c for c in cases}
        # Skeptic: input for the agent, then the join of its objections (REQ-SKEP)
        tour = _zombie_ids(out / "stats" / "judge_tour.json")
        sample_ids = _validation_ids(root / "data" / "labels" / "validation_sample.csv")
        write_input(processed / "skeptic_input.json", build_input(result.zombies, by_id, version, sample_ids, tour))
        result.zombies = join_objections(result.zombies, root / "data" / "labels" / "skeptic_objections.json", p)
        report.excluded_pairs = dict(result.excluded_pairs)
        report.tier_counts = {t: result.count(t) for t in ("headline", "source_unknown", "sensitivity")}  # type: ignore[arg-type]
        report.city_origin = city_origin_summary(result, by_id)
        report.planned_followups = len(result.planned_followups)
        co = report.city_origin
        if co["headline"] and co["city_originated_share"] >= CITY_SHARE_WARN:
            report.warnings.append(
                f"{co['city_originated_share']:.0%} of headline resurrections ({co['city_originated']} of {co['headline']}) "
                f"are legacy city-originated cases; {co['city_originated_under_1h']} opened under 1 h after the closure"
            )
        for z in result.zombies:  # PII counts over the free text that the cards export
            for cid in exported_case_ids(z, by_id):
                pii.scrub(by_id[cid].closure_text)
                pii.scrub(by_id[cid].street)
        report.pii_counts = dict(sorted(pii.counts.items()))
        # stats (durability-stats), when present (REQ-STAT-EXP.1). Only an absent stats package or its pipeline module means
        # "not present": a dependency missing inside the package (even undead311.stats.rates), or any error in run_stats,
        # fails the run. The "not present" branch also removes stats files an earlier run left behind (ops#48).
        stats_status = None
        try:
            stats = importlib.import_module("undead311.stats.pipeline")
        except ModuleNotFoundError as e:
            if e.name not in STATS_ABSENT_NAMES:
                raise
            report.stats = "not present"
            for name in STATS_STALE_FILES:
                (out / "stats" / name).unlink(missing_ok=True)
        else:
            stats_status = stats.run_stats(  # type: ignore[attr-defined]
                con, result, by_id, out, params=p, data_version=version, labels_dir=root / "data" / "labels",
                data_end=max((c.open_utc for c in cases), default=None),
                dataset=dataset,
            )
            report.stats = "ran"
        ctx = ExportContext(
            data_version=version,
            run_time=run_time or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            row_counts=dict(report.row_counts),
            anomalies=list(report.warnings),
            segments="missing",
            exclusion_counts=dict(report.exclusions),
            excluded_ids=excluded,
            stats_status=stats_status,
            dataset=dataset,
            city_origin=report.city_origin,
            data_end=max(c.open_utc for c in cases).strftime("%Y-%m-%d") if cases else None,
        )
        state["files"] = export_all(result, by_id, out, ctx)
        # persist the detector output beside the cases for the MCP server and the stats stage
        con.execute("create table zombies(zombie_id varchar, incident_id varchar, resurrection_id varchar, tier varchar, "
                    "reports_after integer, gap_days double, chain_id varchar, times_risen integer)")  # fmt: skip
        rows = [(z.zombie_id, z.incident_id, z.resurrection_id, z.tier, z.reports_after, z.gap_days, z.chain_id,
                 z.times_risen) for z in result.zombies]  # fmt: skip
        if rows:
            con.executemany("insert into zombies values (?,?,?,?,?,?,?,?)", rows)

    write_duckdb_atomic(processed / "undead311.duckdb", build)
    report.file_sizes = {str(f.relative_to(out)): f.stat().st_size for f in state.get("files", [])}
    report.seconds = time.time() - t0
    write_text_atomic(processed / "run_report.json", canonical_json(report.to_json()))
    return report


__all__ = ["RunReport", "run_pipeline"]
