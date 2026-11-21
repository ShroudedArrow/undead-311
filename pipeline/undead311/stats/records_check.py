"""Records-based check of the validation sample (REQ-STAT-VAL.5, owner decision 2026-11-21 in docs/DECISIONS.md).

No field visits were made, so the 50-site validation sample (`data/labels/validation_sample.csv`, seed 311) is checked against
the city's own records instead: for each sampled possible zombie, how was the RE-REPORT closed? This measures what crews
recorded, not what is on the street. There is one reader (the code below), so no inter-rater agreement exists.

Classes (one per zombie; `CLASSES`):
* `repaired_again`: closed, and the Coroner label of the re-report's closure is `resolved`.
* `duplicate`: closed as a duplicate of another case.
* `invalid_or_nothing_found`: Coroner label `invalid` or `noted` (closed without a repair, for example "no issue found").
* `referred`: Coroner label `referred` (handed to another agency or owner, including a Transitioned closure).
* `still_open`: the re-report is not closed.
* `other`: made safe or temporary, planned follow-up, bulk backlog, or no label.

Ambiguous cases (listed separately, never counted in the main "repaired again" figure; `AMBIGUOUS_REASONS`):
* `code_only`: labeled `resolved` from the closure code alone, with no text saying what was done;
* `conflicting_cue`: labeled `resolved` but the text also carries a cue that no repair was made by crews (violation issued,
  contractor or utility notified, inspected, scheduled, private property, unable to locate, duplicate, temporary);
* `temporary`: Coroner label `made_safe_temporary` (a repair of unknown permanence);
* `planned_followup`: the closure says more work is planned;
* `unlabeled`: the Coroner has no label for the text.
The rules were written before the 50 closures were read.

Reported: the share `repaired_again` of all sampled zombies (Wilson 95% interval), a range that adds the ambiguous cases that
could count as repairs, the same share by case type, and the share among closed re-reports. The set of `record-confirmed`
zombies (repaired again, not ambiguous) feeds the judge tour (`judging_final.py`), labeled as record-confirmed.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from undead311.coroner.join import assign_label_source
from undead311.coroner.templates import mask_template
from undead311.ingest.pii import scrub_text
from undead311.stats.intervals import make_rate

RECORDS_FILE = "validation_records.csv"
CLASSES = ("repaired_again", "duplicate", "invalid_or_nothing_found", "referred", "still_open", "other")
AMBIGUOUS_REASONS = ("code_only", "conflicting_cue", "temporary", "planned_followup", "unlabeled")
RECORD_COLUMNS = (
    "zombie_id", "resurrection_id", "type_family", "neighborhood", "system", "status", "status_at_snapshot", "closure_code",
    "coroner_label", "label_source", "closure_text", "class", "ambiguous_reason", "checked_on",
)  # fmt: skip
HIDE_BELOW = 5  # a closure note is committed only if its masked, scrubbed text is shared by this many closed cases (owner rule)
START = "<!-- records-validation:start -->"
END = "<!-- records-validation:end -->"
CONFLICT = re.compile(
    r"violation|notified|schedul|inspect|temporar|referr|private|owner|unable|cannot|could not|not (?:found|necessary)|duplicate|"
    r"no (?:issue|trouble|problem|violation)|will be|to be (?:done|repaired)|reallocat|utility|contractor",
    re.IGNORECASE,
)
LABEL_CLASS = {
    "resolved": "repaired_again", "duplicate": "duplicate", "invalid": "invalid_or_nothing_found",
    "noted": "invalid_or_nothing_found", "referred": "referred",
}  # fmt: skip


@dataclass(frozen=True)
class Classified:
    label: str
    source: str
    klass: str
    ambiguous: str


def classify(system: str, status: str, code: str | None, text: str | None, table: dict[str, str]) -> Classified:
    """Class and ambiguity of one re-report closure, from its Coroner label (same precedence as the pipeline) and its text."""
    if status != "Closed":
        return Classified("", "none", "still_open", "")
    clean = scrub_text(text) or ""
    label, unlabeled, source = assign_label_source(system, code, mask_template(clean), table)
    klass = LABEL_CLASS.get(label, "other")
    reason = ""
    if unlabeled or label == "other":
        reason = "unlabeled"
    elif label == "made_safe_temporary":
        reason = "temporary"
    elif label == "planned_followup":
        reason = "planned_followup"
    elif label == "resolved":
        if not clean.strip() or clean.strip().lower() in {"resolved", "resolved successfully"}:
            reason = "code_only"
        elif CONFLICT.search(clean):
            reason = "conflicting_cue"
    return Classified(label, source, klass, reason)


def count_classes(rows: list[dict]) -> dict:
    """Counts and rates for the report; every rate has a Wilson interval (n = all rows unless named `closed`)."""
    n = len(rows)
    sure = [r for r in rows if r["class"] == "repaired_again" and not r["ambiguous_reason"]]
    amb = [r for r in rows if r["ambiguous_reason"]]
    could = [r for r in amb if r["class"] == "repaired_again" or r["ambiguous_reason"] == "temporary"]
    closed = [r for r in rows if r["class"] != "still_open"]
    by_type: dict[str, dict] = {}
    for fam in sorted({r["type_family"] for r in rows}):
        part = [r for r in rows if r["type_family"] == fam]
        k = sum(1 for r in part if r in sure)
        by_type[fam] = {"n": len(part), "repaired_again": k, "rate": make_rate(k, len(part)).to_json()}
    return {
        "n": n, "classes": {c: sum(1 for r in rows if r["class"] == c) for c in CLASSES},
        "repaired_again": make_rate(len(sure), n).to_json(),
        "repaired_again_with_ambiguous": make_rate(len(sure) + len(could), n).to_json(),
        "repaired_again_of_closed": make_rate(len(sure), len(closed)).to_json(),
        "by_type": by_type, "ambiguous_ids": [r["zombie_id"] for r in amb],
        "ambiguous_reasons": dict(Counter(r["ambiguous_reason"] for r in amb)),
        "confirmed": sorted(r["zombie_id"] for r in sure),
    }  # fmt: skip


def read_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return sorted(csv.DictReader(f), key=lambda r: r["zombie_id"])


def write_records(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RECORD_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["zombie_id"]))


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _rate(r: dict) -> str:
    return f"{_pct(r['rate'])} ({r['k']} of {r['n']}), Wilson 95% interval {_pct(r['lo'])} to {_pct(r['hi'])}"


def render_section(rows: list[dict], checked_on: str) -> str:
    """The marked block written to docs/VALIDATION.md. Same inputs, same bytes."""
    s = count_classes(rows)
    lines = [START, "## Records-based check of the validation sample", ""]
    if not rows:
        lines += [f"Not run: `data/labels/{RECORDS_FILE}` is missing.", END]
        return "\n".join(lines) + "\n"
    lines += [
        (f"No field visits were made. The {s['n']} sampled possible zombies (`data/labels/validation_sample.csv`, seed 311) were "
        f"checked against the city's records on {checked_on}: how was each re-report closed? This measures what crews "
        "recorded, not what is on the street, and a closure recorded as a repair can still be wrong. One reader classified the "
        "closures by rule, so there is no inter-rater agreement."),
        "",
        f"- Repaired again, not ambiguous: {_rate(s['repaired_again'])}.",
        f"- Range if ambiguous repairs also count: up to {_rate(s['repaired_again_with_ambiguous'])}.",
        f"- Among re-reports already closed: {_rate(s['repaired_again_of_closed'])}.",
        "",
        "| class | cases | of which ambiguous |", "|---|---|---|",
        *[f"| {c.replace('_', ' ')} | {s['classes'][c]} | {sum(1 for r in rows if r['class'] == c and r['ambiguous_reason'])} |" for c in CLASSES],
        "",
        "Repaired again by case type (small groups, wide intervals):",
        "",
        "| case type | cases | repaired again | share, 95% interval |", "|---|---|---|---|",
        *[f"| {f.replace('_', ' ')} | {v['n']} | {v['repaired_again']} | {_pct(v['rate']['rate'])} ({_pct(v['rate']['lo'])} to {_pct(v['rate']['hi'])}) |"
          for f, v in s["by_type"].items()],
        "",
        f"Ambiguous cases ({len(s['ambiguous_ids'])}), listed apart and left out of the main figure:",
        "",
        "| zombie | type | class | reason |", "|---|---|---|---|",
        *[f"| {r['zombie_id']} | {r['type_family'].replace('_', ' ')} | {r['class'].replace('_', ' ')} | {r['ambiguous_reason'].replace('_', ' ')} |"
          for r in rows if r["ambiguous_reason"]],
        "",
        f"Record-confirmed zombies (repaired again, not ambiguous): {len(s['confirmed'])}.",
        END,
    ]  # fmt: skip
    return "\n".join(lines) + "\n"


def write_section(validation_md: Path, section: str) -> None:
    p = Path(validation_md)
    text = p.read_text(encoding="utf-8") if p.is_file() else "# Validation\n"
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    new = pattern.sub(lambda _m: section, text) if pattern.search(text) else text.rstrip("\n") + "\n\n" + section
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8")
