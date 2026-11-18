"""`make judging-final`: after the field labels exist, regenerate ONLY the validation and judge-mode files and amend the
judging section, for the final tag before the Dec 2 freeze (REQ-OPS-SNAP.4).

  python pipeline/scripts/judging_final.py --run-id full-4 [--dry-run]

The Friday snapshot freezes the data with `stats/validation.json` saying `awaiting_field_labels` and a provisional judge tour
(`make snapshot RUN_ID=full-4`, stage provisional). When `data/labels/validation_labels.csv` holds two raters' labels, this script:

1. scores the labels (`undead311.stats.validation`) and builds the tour from the confirmed zombies, with the owner's override
   `data/labels/judge_tour_override.json` when it lists three confirmed ones; it stops, changing nothing, while no pair of
   raters has labeled a zombie or fewer than three zombies are confirmed;
2. rewrites `stats/validation.json` and `stats/judge_tour.json` in the run's export folder (schema-checked first) and the
   field-validation block of `docs/VALIDATION.md`. No other export file, no database and no raw file is touched;
3. rebuilds the judging section (stage final, tag `judged-<data end>-final`) and refuses to write it unless exactly those two
   files, and nothing else, changed their hash row (anything else means the exports drifted since the first snapshot; the two
   files are put back and nothing is written);
4. replaces the judge-mode files in `data/judging/` (the new tour's three card shards come with it).

It never tags, pushes or publishes. It prints the next steps: commit `data/SNAPSHOT.md`, `data/judging/` and
`docs/VALIDATION.md`, tag, and publish the run's exports again (`exports_release.py publish --run-id <run>`; the run's release
asset is replaced) so the live site's Methods page shows the same validation numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from undead311 import snapshot as snap
from undead311.export.writers import canonical_json, validate, write_text_atomic
from undead311.paths import data_dir
from undead311.stats import validation as val
from undead311.stats.pipeline import OVERRIDE_FILE
from undead311.stats.tour import build_tour, read_override

CHECKOUT = HERE.parents[1]
ALLOWED = {snap.PUBLIC_PREFIX + snap.VALIDATION, snap.PUBLIC_PREFIX + snap.JUDGE_TOUR}


class FinalError(SystemExit):
    """A reason to stop; nothing has been changed when it is raised before the files are written."""


def plan(public: Path, labels_dir: Path) -> tuple[dict, dict, val.Validation]:
    """The new validation.json and judge_tour.json payloads, or a FinalError (REQ-OPS-SNAP.4)."""
    old_val = json.loads((public / snap.VALIDATION).read_text())
    old_tour = json.loads((public / snap.JUDGE_TOUR).read_text())
    v = val.score(val.read_sample_ids(labels_dir / val.SAMPLE_FILE), val.read_labels(labels_dir / val.LABELS_FILE))
    if v.status != "scored":
        raise FinalError("judging-final: awaiting field labels (no zombie has two raters' labels in "
                         f"{labels_dir / val.LABELS_FILE}); nothing changed, the tour stays provisional")
    records = val.read_zombie_records(public / "zombies.json")
    if records is None:
        raise FinalError(f"judging-final: {public}/zombies/ is missing; is this the run's export folder?")
    zombies = [SimpleNamespace(**r) for r in records]
    tour = build_tour(zombies, read_override(labels_dir / OVERRIDE_FILE), v.confirmed)
    if tour is None or tour.provisional:
        raise FinalError(f"judging-final: {len(v.confirmed)} confirmed zombies; a final tour needs at least 3 "
                         "(both raters: still broken). Nothing changed, the tour stays provisional")
    version, dataset = old_tour["data_version"], old_tour["dataset"]
    if old_val["data_version"] != version:
        raise FinalError("judging-final: validation.json and judge_tour.json disagree on data_version; not touching them")
    new_val = {**v.to_json(version), "dataset": dataset, "params": old_val["params"], "seed": None}
    new_tour = {**tour.to_json(version, dataset=dataset), "params": old_tour["params"]}
    validate("validation", new_val)
    validate("judge_tour", new_tour)
    return new_val, new_tour, v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--labels-dir", type=Path, default=CHECKOUT / "data" / "labels")
    ap.add_argument("--validation-md", type=Path, default=CHECKOUT / "docs" / "VALIDATION.md")
    ap.add_argument("--snapshot", type=Path, default=CHECKOUT / "data" / "SNAPSHOT.md")
    ap.add_argument("--judging", type=Path, default=None, help="default: judging/ beside --snapshot")
    ap.add_argument("--public", type=Path, default=None, help="the run's export folder (default $DATA_DIR/exports/<run-id>)")
    ap.add_argument("--processed", type=Path, default=None, help="default $DATA_DIR/processed")
    ap.add_argument("--raw", type=Path, default=None, help="default: the raw folder beside --processed")
    ap.add_argument("--dry-run", action="store_true", help="say what would change; write nothing")
    a = ap.parse_args(argv)
    public = a.public or data_dir() / "exports" / a.run_id
    processed = a.processed or data_dir() / "processed"
    raw = a.raw or processed.parent / "raw"
    judging = a.judging or a.snapshot.parent / snap.JUDGING_DIR
    text = a.snapshot.read_text() if a.snapshot.is_file() else ""
    section = snap.extract_section(text)
    if section is None or f"Run: `{a.run_id}`" not in section:
        raise FinalError(f"judging-final: {a.snapshot} has no judging section for run {a.run_id}; run `make snapshot RUN_ID={a.run_id}` first")
    snap.check_run(public, processed, a.run_id)
    old_rows = snap.section_rows(text)
    new_val, new_tour, v = plan(public, a.labels_dir)

    paths = {public / snap.VALIDATION: canonical_json(new_val), public / snap.JUDGE_TOUR: canonical_json(new_tour)}
    backup = {p: p.read_text(encoding="utf-8") for p in paths}
    try:
        for p, body in paths.items():
            write_text_atomic(p, body)
        new_section = snap.build(public, processed, None, None, raw, run_id=a.run_id, stage="final")
        new_rows = snap.section_rows(new_section)
        changed = snap.row_changes(old_rows, new_rows)
        stray = sorted(set(changed) - ALLOWED)
        if stray:
            raise FinalError("judging-final: the exports changed since the snapshot besides the validation and tour files: "
                             + ", ".join(f"{k} ({changed[k]})" for k in stray[:8]) + ". Nothing was written")
        if a.dry_run:
            print(f"judging-final (dry run): would change {sorted(changed)}; tour {new_tour['zombie_ids']}")
            raise _Undo
        new_text = snap.upsert_section(text, new_section)
        snap.commit_judging(public, judging, new_text)
        val.write_section(a.validation_md, val.render_section(v))
        a.snapshot.write_text(new_text)
    except (_Undo, SystemExit, Exception) as exc:  # put the two export files back unless everything was written
        for p, body in backup.items():
            write_text_atomic(p, body)
        if isinstance(exc, _Undo):
            return 0
        raise
    tag = snap.recorded_tag_and_stage(new_text)[0]
    p = v.precision or {}
    print(f"judging-final: {v.n_paired} labeled pairs, precision {p.get('rate')} ({p.get('k')} of {p.get('n')}), "
          f"{len(v.confirmed)} confirmed; tour {new_tour['zombie_ids']}")
    print(f"judging-final: changed {sorted(changed)}; judge-mode files in {judging}; {a.validation_md} updated")
    print(f"judging-final: next, commit data/SNAPSHOT.md, data/judging/ and docs/VALIDATION.md, then "
          f"git tag -a {tag} -m 'Final judging snapshot' && git push origin {tag}")
    print(f"judging-final: then publish the run again so the live Methods page matches: "
          f"python pipeline/scripts/exports_release.py publish --run-id {a.run_id}; and set JUDGED_TAG to {tag}")
    return 0


class _Undo(Exception):
    """Dry run: restore the export files and leave."""


if __name__ == "__main__":
    sys.exit(main())
