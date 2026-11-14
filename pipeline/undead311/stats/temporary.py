"""How often temporary fixes come back, separate deaths and exclusions (REQ-STAT-TEMP, zombie-definition steps 6 and 8).

Cohort: eligible originals (cohort.py, core scope) whose Coroner label is `made_safe_temporary`. Of those, the share that
became a headline possible zombie tagged `after_temporary_fix` (a resident re-reported a legacy case) and, shown
separately, the share tagged `source_unknown` (a new-system re-report, whose origin is unknown). Both carry Wilson
intervals and the cohort size. Rows are per family, per department, and citywide (`family` "all").
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime

from undead311.detect.model import DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.stats.cohort import eligible_originals
from undead311.stats.intervals import make_rate
from undead311.stats.meta import params_json

MADE_SAFE = "made_safe_temporary"


def temporary_rows(result: DetectionResult, data_end: datetime, params: Params = DEFAULT) -> list[dict]:
    """One row per (family, department) with `n_made_safe`, `after_temporary_fix` and `source_unknown` rates (REQ-STAT-TEMP.1)."""
    z_by_inc = {z.incident_id: z for z in result.zombies}
    cells: dict[tuple[str, str | None], list[int]] = defaultdict(lambda: [0, 0, 0])  # n, after_temporary_fix, source_unknown
    for inc in eligible_originals(result.incidents, data_end, params):
        if inc.coroner_label != MADE_SAFE:
            continue
        z = z_by_inc.get(inc.incident_id)
        flags = (
            int(z is not None and z.tier == "headline" and z.after_temporary_fix),
            int(z is not None and z.source_unknown),
        )
        for key in ((inc.type_family, None), (inc.type_family, inc.department or "(unknown)"),
                    ("all", None), ("all", inc.department or "(unknown)")):  # fmt: skip
            cell = cells[key]
            cell[0] += 1
            cell[1] += flags[0]
            cell[2] += flags[1]
    return [
        {
            "family": fam, "department": dept, "n_made_safe": n,
            "after_temporary_fix": make_rate(a, n).to_json(), "source_unknown": make_rate(u, n).to_json(),
        }
        for (fam, dept), (n, a, u) in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))
    ]  # fmt: skip


def separate_death_counts(result: DetectionResult) -> dict[str, int]:
    """Incidents labeled `invalid` or `duplicate` that were re-reported: a different kind of death (REQ-STAT-TEMP.2)."""
    c = Counter(d.label for d in result.separate_deaths)
    return {"duplicate": c.get("duplicate", 0), "invalid": c.get("invalid", 0)}


def temporary_payload(
    result: DetectionResult, data_end: datetime, data_version: str, params: Params, dataset: str,
    exclusions: Mapping[str, int] | None = None,
) -> dict:
    """The `temporary_fixes.json` payload; `exclusions` merges the cleaning counts and the excluded-pair counts."""
    merged = {**{k: int(v) for k, v in (exclusions or {}).items()}, **{f"pair_{k}": int(v) for k, v in result.excluded_pairs.items()}}
    return {
        "data_version": data_version, "dataset": dataset, "params": params_json(params), "seed": None,
        "rows": temporary_rows(result, data_end, params), "separate_deaths": separate_death_counts(result),
        "exclusions": dict(sorted(merged.items())),
    }  # fmt: skip
