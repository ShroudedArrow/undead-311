"""Coroner label join (REQ-COR-1.2-1.4).

Precedence for a closed case: (1) new-system closure code Transitioned -> `referred`; (2) the template label from
`data/labels/coroner_labels.csv`; (3) for new-system closures, `NEW_SYSTEM_CLOSURE_LABELS` by code; (4) `other`,
counted as `unlabeled`. Labels outside the allowed set are rejected (REQ-COR-1.4).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import duckdb

from undead311.coroner.templates import mask_template
from undead311.ingest.closure_flags import new_system_closure_label

ALLOWED_LABELS = (
    "resolved", "noted", "invalid", "duplicate", "referred", "made_safe_temporary", "planned_followup",
    "bulk_backlog", "other",
)  # fmt: skip


class UnknownLabel(ValueError):
    """A label outside ALLOWED_LABELS (REQ-COR-1.4)."""


def check_label(label: str) -> str:
    if label not in ALLOWED_LABELS:
        raise UnknownLabel(f"label {label!r} is not one of {', '.join(ALLOWED_LABELS)}")
    return label


def load_template_labels(path: Path | None) -> dict[str, str]:
    """Template -> label from a `template,label` CSV; a missing file gives {} (every closure is then `other`)."""
    if path is None or not Path(path).is_file():
        return {}
    labels: dict[str, str] = {}
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            labels[row["template"]] = check_label(row["label"].strip())
    return labels


def assign_label(
    system: str, closure_code: str | None, template: str, template_labels: dict[str, str]
) -> tuple[str, bool]:
    """(label, unlabeled) by the precedence above (REQ-COR-1.2-1.3)."""
    code_label = new_system_closure_label(closure_code) if system == "new" else None
    if code_label == "referred":
        return "referred", False
    if template in template_labels:
        return check_label(template_labels[template]), False
    if code_label:
        return check_label(code_label), False
    return "other", True


@dataclass
class JoinReport:
    closed_in_scope: int = 0
    unlabeled: int = 0
    labels_file_missing: bool = False

    @property
    def covered_share(self) -> float:
        return 1.0 if not self.closed_in_scope else 1 - self.unlabeled / self.closed_in_scope


def join_labels(con: duckdb.DuckDBPyConnection, labels_csv: Path | None, table: str = "cases_clean") -> JoinReport:
    """Set `coroner_label` on every closed case of `table`; open cases keep NULL."""
    template_labels = load_template_labels(labels_csv)
    report = JoinReport(labels_file_missing=not template_labels and not (labels_csv and Path(labels_csv).is_file()))
    combos = con.execute(
        f"select system, closure_code, closure_text, count(*) from {table} where status = 'Closed' "
        "group by all"
    ).fetchall()
    con.execute("create or replace temp table label_map(system varchar, closure_code varchar, closure_text varchar, label varchar)")
    rows = []
    for system, code, text, n in combos:
        label, unlabeled = assign_label(system, code, mask_template(text), template_labels)
        rows.append((system, code, text, label))
        report.closed_in_scope += n
        report.unlabeled += n if unlabeled else 0
    if rows:
        con.executemany("insert into label_map values (?,?,?,?)", rows)
    con.execute(f"""
        create or replace table {table} as
        select c.* exclude (coroner_label), m.label as coroner_label
        from {table} c
        left join label_map m on c.status = 'Closed' and m.system = c.system
             and m.closure_code is not distinct from c.closure_code
             and m.closure_text is not distinct from c.closure_text
        order by c.id, c.system
    """)
    con.execute("drop table label_map")
    return report


def unlabeled_templates(
    con: duckdb.DuckDBPyConnection, labels_csv: Path | None, top: int = 300, table: str = "cases_clean"
) -> tuple[list[dict], dict]:
    """The `top` most common closure templates that no label covers, and a coverage summary (REQ-COR-1.3, REQ-OPS-RUN.5).

    Uses the same rule as `join_labels` (`assign_label`): a closed case is unlabeled when its masked template is not in the
    label table and the new-system closure code gives no label. Rows are `template, n_cases, example_id, systems, example_text`,
    sorted by n_cases (descending) then template. The summary has the closed in-scope count, the unlabeled count, coverage,
    the split by system, and how many unlabeled cases the listed templates account for."""
    template_labels = load_template_labels(labels_csv)
    groups = con.execute(
        f"select system, closure_code, closure_text, count(*), min(id) from {table} where status = 'Closed' group by all"
    ).fetchall()
    merged: dict[str, dict] = {}
    closed = {"legacy": 0, "new": 0}
    missed = {"legacy": 0, "new": 0}
    for system, code, text, n, example_id in groups:
        template = mask_template(text)
        _label, unlabeled = assign_label(system, code, template, template_labels)
        closed[system] = closed.get(system, 0) + n
        if not unlabeled:
            continue
        missed[system] = missed.get(system, 0) + n
        slot = merged.setdefault(template, {"template": template, "n_cases": 0, "example_id": example_id,
                                            "systems": {}, "example_text": text or "", "_best": 0})  # fmt: skip
        slot["n_cases"] += n
        slot["systems"][system] = slot["systems"].get(system, 0) + n
        if n > slot["_best"]:
            slot["_best"], slot["example_id"], slot["example_text"] = n, example_id, text or ""
    ranked = sorted(merged.values(), key=lambda r: (-r["n_cases"], r["template"]))[:top]
    rows = [
        {"template": r["template"] or "(empty closure text)", "n_cases": r["n_cases"], "example_id": r["example_id"],
         "systems": ";".join(f"{k}:{v}" for k, v in sorted(r["systems"].items())), "example_text": r["example_text"][:300]}
        for r in ranked
    ]  # fmt: skip
    total, miss = sum(closed.values()), sum(missed.values())
    summary = {
        "closed_in_scope": total, "unlabeled": miss, "coverage": 1.0 if not total else 1 - miss / total,
        "closed_by_system": closed, "unlabeled_by_system": missed,
        "coverage_by_system": {k: (1.0 if not closed[k] else 1 - missed[k] / closed[k]) for k in closed},
        "distinct_unlabeled_templates": len(merged), "listed_templates": len(rows),
        "listed_cases": sum(r["n_cases"] for r in rows),
        "coverage_if_listed_were_labeled": 1.0 if not total else 1 - (miss - sum(r["n_cases"] for r in rows)) / total,
    }  # fmt: skip
    return rows, summary
