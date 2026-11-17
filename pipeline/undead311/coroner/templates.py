"""Closure-text templates for the Coroner agent (REQ-COR-1.1).

`mask_template` replaces timestamps, dates, case IDs and numbers with placeholders, lower-cases the text and collapses
whitespace, so the thousands of templated closure texts collapse to a short list. `build_templates` counts the closed
in-scope cases per template and writes `coroner_templates.csv` (template, n_cases, example_id), sorted by n_cases.
The label table `data/labels/coroner_labels.csv` (columns `template,label`) is keyed by the same masked text.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import duckdb

from undead311.ingest.pii import scrub_text

_TS = re.compile(
    r"\d{4}-\d{2}-\d{2}[ t]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"  # 2026-05-01 08:57:13.83
    r"|(?:mon|tue|wed|thu|fri|sat|sun)\s+[a-z]{3}\s+\d{1,2}\s+\d{1,2}:\d{2}:\d{2}\s+[a-z]{2,4}\s+\d{4}"  # Fri Jan 02 ... EST 2015
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
_CASE_ID = re.compile(r"bcs-?\d+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_DATE_PREFIX = re.compile(r"closed date\s*:\s*<ts>\s*\.?\s*")
_SPACE = re.compile(r"\s+")


def mask_template(text: str | None) -> str:
    """Mask timestamps, dates, numbers and case IDs (REQ-COR-1.1). Empty or missing text gives ''."""
    if not text:
        return ""
    s = text.lower()
    s = _TS.sub("<ts>", s)
    s = _DATE_PREFIX.sub("", s)
    s = _DATE.sub("<date>", s)
    s = _CASE_ID.sub("<case>", s)
    s = _NUMBER.sub("<n>", s)
    return _SPACE.sub(" ", s).strip(" .:")


def label_key(template: str) -> str:
    """The key the label table is read by: the masked template with signatures, sign-offs and staff names scrubbed
    (REQ-ING-PII.4, .6). The committed table holds only scrubbed keys, so no staff name is in the repository; a raw template
    is scrubbed the same way before it is looked up, so both sides meet at the same key. Idempotent."""
    return scrub_text(template) or ""


def build_templates(con: duckdb.DuckDBPyConnection, out_dir: Path, table: str = "cases_clean") -> Path:
    """Write `coroner_templates.csv` for the closed in-scope cases in `table`; return its path."""
    rows = con.execute(
        f"select closure_text, count(*), min(id) from {table} where status = 'Closed' and closure_text is not null "
        "group by 1"
    ).fetchall()
    merged: dict[str, list] = {}
    for text, n, example in rows:
        t = mask_template(text)
        if not t:
            continue
        slot = merged.setdefault(t, [0, example])
        slot[0] += n
        slot[1] = min(slot[1], example)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "coroner_templates.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["template", "n_cases", "example_id"])
        for t, (n, ex) in sorted(merged.items(), key=lambda kv: (-kv[1][0], kv[0])):
            w.writerow([t, n, ex])
    return path
