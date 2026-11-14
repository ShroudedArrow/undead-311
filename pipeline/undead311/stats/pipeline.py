"""Stats stage called by the engine pipeline after detection (design "Run order"). REQ-STAT-EXP.1.

Writes `scorecard.json` and `judge_tour.json` (demo-critical) to `<out>/stats/`, each validated against its schema
before anything is written, and `stats_status.json` (the engine folds it into `status.json`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from undead311.detect.model import Case, DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.export.writers import canonical_json, validate, write_text_atomic
from undead311.stats.rates import scorecard_payload, scorecards
from undead311.stats.tour import build_tour, read_override

OVERRIDE_FILE = "judge_tour_override.json"
STAT_FILES = ("scorecard.json", "judge_tour.json")  # demo-critical outputs; one that is not produced is removed


def build_stats(
    result: DetectionResult,
    cases: Mapping[str, Case],
    data_version: str,
    data_end: datetime,
    params: Params = DEFAULT,
    labels_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(payloads by file name, status) for the stats stage, unvalidated."""
    payloads: dict[str, Any] = {
        "scorecard.json": scorecard_payload(
            scorecards(result, cases, data_end, params), result, data_version, params
        )
    }
    status: dict[str, Any] = {"calibration_warning": None, "warnings": []}
    override = read_override(labels_dir / OVERRIDE_FILE) if labels_dir else None
    tour = build_tour(result.zombies, override)
    if tour is None:
        status["warnings"].append("judge_tour.json not written: fewer than 3 headline zombies")
    else:
        payloads["judge_tour.json"] = tour.to_json(data_version, params)
        if override is not None and tour.source != "override":
            status["warnings"].append(f"{OVERRIDE_FILE} ignored: it must list 3 distinct headline zombie IDs")
    return payloads, status


def run_stats(
    con: Any,
    result: DetectionResult,
    by_id: Mapping[str, Case],
    out: Path,
    *,
    params: Params = DEFAULT,
    data_version: str = "unknown",
    data_end: datetime | None = None,
    labels_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate, then write the stats files under `<out>/stats/` (REQ-STAT-EXP.1). Returns the stats status."""
    end = data_end or max((c.open_utc for c in by_id.values()), default=None)
    folder = Path(out) / "stats"
    if end is None:
        payloads: dict[str, Any] = {}
        status: dict[str, Any] = {"calibration_warning": None, "warnings": ["no cases"]}
    else:
        payloads, status = build_stats(result, by_id, data_version, end, params, labels_dir)
        for name, payload in payloads.items():
            validate(name.removesuffix(".json"), payload)
    for name in sorted(payloads):
        write_text_atomic(folder / name, canonical_json(payloads[name]))
    for name in STAT_FILES:  # a file from an earlier run must not outlive a run that did not produce it
        if name not in payloads:
            (folder / name).unlink(missing_ok=True)
    write_text_atomic(folder / "stats_status.json", canonical_json(status))
    return status
