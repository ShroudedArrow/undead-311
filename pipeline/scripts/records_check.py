"""`make records-check`: classify how each sampled zombie's re-report was closed (REQ-STAT-VAL.5).

  python pipeline/scripts/records_check.py --raw DIR [--exports DIR] [--checked-on YYYY-MM-DD]

Reads the 50 sampled zombies (`data/labels/validation_sample.csv`), finds each re-report in the raw 311 files in `--raw`
(`new_system.csv` and the yearly legacy files, any file name with a `case_id` or `case_enquiry_id` column), labels its closure
with the Coroner (label table, closure code, leading phrases; `undead311.coroner.join`) and writes
`data/labels/validation_records.csv` plus the records block of `docs/VALIDATION.md`. A closure note is written only when its
masked, scrubbed text is shared by at least 5 closed cases in the raw file (the cards' rule); other notes show as hidden.
With `--exports` (the run's export folder) the re-report's status in the frozen snapshot is recorded too, so a closure that came
after the snapshot is visible. Refuses to overwrite an existing records file unless `--force` (the check is run once).
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from undead311.coroner.join import load_template_labels
from undead311.coroner.templates import mask_template
from undead311.ingest.pii import scrub_text
from undead311.stats import records_check as rc
from undead311.stats import validation as val

CHECKOUT = HERE.parents[1]


def find_rows(raw: Path, ids: set[str]) -> tuple[dict[str, dict], Counter]:
    """id -> row for the wanted ids, and the count of closed cases per masked, scrubbed note across the new-system file."""
    found: dict[str, dict] = {}
    shared: Counter = Counter()
    for path in sorted(raw.glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                new = "case_id" in r
                cid = (r.get("case_id") if new else r.get("case_enquiry_id")) or ""
                if new:
                    text = (r.get("closure_comments") or "").strip() or (r.get("closure_reason") or "").strip()
                else:
                    text = (r.get("closure_reason") or "").strip()
                if r.get("case_status") == "Closed" and text:
                    shared[mask_template(scrub_text(text))] += 1
                if cid in ids:
                    found[cid] = {"system": "new" if new else "legacy", "status": r.get("case_status") or "",
                                  "code": (r.get("closure_reason") or "").strip() if new else None, "text": text}  # fmt: skip
    return found, shared


def snapshot_status(exports: Path | None, ids: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if exports is None:
        return out
    for f in glob.glob(str(exports / "cards" / "*.json")):
        for c in json.loads(Path(f).read_text())["cards"]:
            if c["zombie_id"] in ids:
                out[c["zombie_id"]] = c["rereport"]["status"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--exports", type=Path, default=None)
    ap.add_argument("--checked-on", required=True)
    ap.add_argument("--labels-dir", type=Path, default=CHECKOUT / "data" / "labels")
    ap.add_argument("--validation-md", type=Path, default=CHECKOUT / "docs" / "VALIDATION.md")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    target = a.labels_dir / rc.RECORDS_FILE
    if target.is_file() and not a.force:
        print(f"records-check: {target} exists; the check is run once. Use --force to redo it", file=sys.stderr)
        return 2
    with (a.labels_dir / val.SAMPLE_FILE).open(newline="") as f:
        sample = sorted(csv.DictReader(f), key=lambda r: r["zombie_id"])
    found, shared = find_rows(a.raw, {r["resurrection_id"] for r in sample})
    missing = [r["resurrection_id"] for r in sample if r["resurrection_id"] not in found]
    if missing:
        print(f"records-check: {len(missing)} re-reports are not in the raw files: {missing}", file=sys.stderr)
        return 2
    snap = snapshot_status(a.exports, {r["zombie_id"] for r in sample})
    table = load_template_labels(a.labels_dir / "coroner_labels.csv")
    rows = []
    for s in sample:
        raw = found[s["resurrection_id"]]
        c = rc.classify(raw["system"], raw["status"], raw["code"], raw["text"], table)
        note = scrub_text(raw["text"]) or ""
        shown = note if shared[mask_template(note)] >= rc.HIDE_BELOW else ("[hidden: fewer than 5 closed cases share this note]" if note else "")
        rows.append({
            "zombie_id": s["zombie_id"], "resurrection_id": s["resurrection_id"], "type_family": s["type_family"],
            "neighborhood": s["neighborhood"], "system": raw["system"], "status": raw["status"],
            "status_at_snapshot": snap.get(s["zombie_id"], ""), "closure_code": raw["code"] or "", "coroner_label": c.label,
            "label_source": c.source, "closure_text": shown, "class": c.klass, "ambiguous_reason": c.ambiguous,
            "checked_on": a.checked_on,
        })  # fmt: skip
    rc.write_records(target, rows)
    rc.write_section(a.validation_md, rc.render_section(rc.read_records(target), a.checked_on))
    s = rc.count_classes(rc.read_records(target))
    print(f"records-check: {s['n']} zombies; classes {s['classes']}; repaired again {s['repaired_again']['k']} "
          f"({s['repaired_again']['rate']}); ambiguous {len(s['ambiguous_ids'])}; confirmed {len(s['confirmed'])}")
    drift = sum(1 for r in rows if r["status_at_snapshot"] and r["status_at_snapshot"] != r["status"])
    print(f"records-check: {drift} re-reports changed status since the snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
