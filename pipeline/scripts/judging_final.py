"""`make judging-final`: after the validation labels exist, regenerate ONLY the validation and judge-mode files and amend the
judging section, for the final tag before the Dec 2 freeze (REQ-OPS-SNAP.4).

  python pipeline/scripts/judging_final.py --run-id full-4 [--source auto|field|records] [--dry-run]

The Friday snapshot freezes the data with `stats/validation.json` saying `awaiting_field_labels` and a provisional judge tour
(`make snapshot RUN_ID=full-4`, stage provisional). Two sources of confirmation exist (`--source`, default `auto`: field labels
when they score, else the records check):

* `field`: `data/labels/validation_labels.csv` holds two raters' labels (a zombie is confirmed when both say still broken);
* `records`: `data/labels/validation_records.csv` (written once by `make records-check`; no field visits were made, owner decision
  2026-11-21) says how each sampled zombie's re-report was closed. Zombies whose re-report was repaired again and not ambiguous
  are record-confirmed; the tour file says `confirmation: records` and the site labels the tour as record-confirmed.

This script:

1. scores the chosen source (`undead311.stats.validation`) and builds the tour from the confirmed zombies, with the owner's
   override `data/labels/judge_tour_override.json` when it lists three confirmed ones; it stops, changing nothing, while there is
   no scored source or fewer than three zombies are confirmed (a records tour also needs a re-report of at least 1 hour after the
   closure, and no Skeptic "explained away");
2. rewrites `stats/validation.json` and `stats/judge_tour.json` in the run's export folder (schema-checked first) and the
   field-validation block of `docs/VALIDATION.md`. No other export file, no database and no raw file is touched;
3. rebuilds the judging section (stage final, tag `judged-<data end>-final`) and refuses to write it unless exactly those two
   files, and nothing else, changed their hash row (anything else means the exports drifted since the first snapshot; the two
   files are put back and nothing is written);
4. replaces the judge-mode files in `data/judging/` (the new tour's three card shards come with it).

`--exports-only --archive-sha256 <hex>` (REQ-OPS-SNAP.5) is for a machine that has no `raw/` or `processed/` folder. Instead of
re-hashing them it downloads the release `exports-<run-id>` of the data repo through the REST API (needs `DATA_RELEASE_TOKEN`,
read access is enough; `--transport gh` uses `gh api`, REST only, with gh's own login instead), checks the archive's SHA-256 against the value recorded at the snapshot, unpacks it into a scratch
folder, and requires every `web/public/data/` row of the judging section to equal the unpacked files (extra, missing or changed
files stop it). The raw and processed rows and the DuckDB table counts are carried over unchanged, and the section says so in a
one-line note. Step 3 still applies: anything besides the two files changing a row stops it, and nothing is written.

It never tags, pushes or publishes. It prints the next steps: commit `data/SNAPSHOT.md`, `data/judging/` and
`docs/VALIDATION.md`, tag, and publish the run's exports again (`exports_release.py publish --run-id <run>`; the run's release
asset is replaced) so the live site's Methods page shows the same validation numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import exports_release as er

from undead311 import snapshot as snap
from undead311.export.writers import canonical_json, validate, write_text_atomic
from undead311.paths import data_dir
from undead311.stats import records_check as rc
from undead311.stats import validation as val
from undead311.stats.pipeline import OVERRIDE_FILE
from undead311.stats.tour import build_tour, read_override

CHECKOUT = HERE.parents[1]
ALLOWED = {snap.PUBLIC_PREFIX + snap.VALIDATION, snap.PUBLIC_PREFIX + snap.JUDGE_TOUR}


class FinalError(SystemExit):
    """A reason to stop; nothing has been changed when it is raised before the files are written."""


def score_source(labels_dir: Path, source: str) -> val.Validation:
    """Score the field labels or the records check; `auto` takes the field labels when they score, else the records."""
    ids = val.read_sample_ids(labels_dir / val.SAMPLE_FILE)
    if source in ("auto", "field"):
        v = val.score(ids, val.read_labels(labels_dir / val.LABELS_FILE))
        if v.status == "scored" or source == "field":
            return v
    return val.score_records(ids, rc.read_records(labels_dir / rc.RECORDS_FILE))


def plan(public: Path, labels_dir: Path, source: str = "auto") -> tuple[dict, dict, val.Validation]:
    """The new validation.json and judge_tour.json payloads, or a FinalError (REQ-OPS-SNAP.4)."""
    old_val = json.loads((public / snap.VALIDATION).read_text())
    old_tour = json.loads((public / snap.JUDGE_TOUR).read_text())
    v = score_source(labels_dir, source)
    if v.status != "scored":
        raise FinalError("judging-final: awaiting field labels or a records check (no zombie has two raters' labels in "
                         f"{labels_dir / val.LABELS_FILE} and {labels_dir / rc.RECORDS_FILE} is missing or empty); "
                         "nothing changed, the tour stays provisional")
    records = val.read_zombie_records(public / "zombies.json")
    if records is None:
        raise FinalError(f"judging-final: {public}/zombies/ is missing; is this the run's export folder?")
    zombies = [SimpleNamespace(**r) for r in records]
    tour = build_tour(zombies, read_override(labels_dir / OVERRIDE_FILE), v.confirmed, "records" if v.method == "records" else "field")
    if tour is None or tour.provisional:
        how = "repaired again in the records" if v.method == "records" else "both raters: still broken"
        raise FinalError(f"judging-final: {len(v.confirmed)} confirmed zombies; a final tour needs at least 3 "
                         f"({how}). Nothing changed, the tour stays provisional")
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
    ap.add_argument("--source", choices=("auto", "field", "records"), default="auto", help="what confirms the tour (default auto)")
    ap.add_argument("--labels-dir", type=Path, default=CHECKOUT / "data" / "labels")
    ap.add_argument("--validation-md", type=Path, default=CHECKOUT / "docs" / "VALIDATION.md")
    ap.add_argument("--snapshot", type=Path, default=CHECKOUT / "data" / "SNAPSHOT.md")
    ap.add_argument("--judging", type=Path, default=None, help="default: judging/ beside --snapshot")
    ap.add_argument("--public", type=Path, default=None, help="the run's export folder (default $DATA_DIR/exports/<run-id>)")
    ap.add_argument("--processed", type=Path, default=None, help="default $DATA_DIR/processed")
    ap.add_argument("--raw", type=Path, default=None, help="default: the raw folder beside --processed")
    ap.add_argument("--dry-run", action="store_true", help="say what would change; write nothing")
    ap.add_argument("--exports-only", action="store_true",
                    help="no raw/ or processed/ here: verify the release exports-<run-id> and carry the raw and processed rows over")
    ap.add_argument("--archive-sha256", default=None, help="with --exports-only: the SHA-256 of the release archive recorded at the snapshot")
    ap.add_argument("--transport", choices=("rest", "gh"), default="rest",
                    help="with --exports-only: rest = direct REST calls with DATA_RELEASE_TOKEN (default); gh = `gh api` REST calls with gh's own login")
    ap.add_argument("--data-repo", default=er.DATA_REPO, help=argparse.SUPPRESS)
    ap.add_argument("--api-url", default=er.API_URL, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.exports_only and (not a.archive_sha256 or a.public or a.processed or a.raw):
        raise FinalError("judging-final: --exports-only needs --archive-sha256 and takes no --public, --processed or --raw")
    if a.archive_sha256 and not a.exports_only:
        raise FinalError("judging-final: --archive-sha256 is only for --exports-only")
    with ExitStack() as stack:
        if a.exports_only:
            scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=data_dir(), prefix=f"exports-only-{a.run_id}-")))
            return run(a, scratch)
        return run(a, None)


def run(a: argparse.Namespace, scratch: Path | None) -> int:
    public = a.public or data_dir() / "exports" / a.run_id
    processed = a.processed or data_dir() / "processed"
    raw = a.raw or processed.parent / "raw"
    judging = a.judging or a.snapshot.parent / snap.JUDGING_DIR
    text = a.snapshot.read_text() if a.snapshot.is_file() else ""
    section = snap.extract_section(text)
    if section is None or f"Run: `{a.run_id}`" not in section:
        raise FinalError(f"judging-final: {a.snapshot} has no judging section for run {a.run_id}; run `make snapshot RUN_ID={a.run_id}` first")
    note = None
    if scratch is not None:
        try:
            er.fetch_release(a.run_id, scratch, a.archive_sha256, a.data_repo, api_url=a.api_url, transport=a.transport)
        except er.ExportsError as exc:
            raise FinalError(f"judging-final: {exc}. Nothing changed") from None
        public, processed = scratch / "exports", None
        snap.check_run(public, None, a.run_id)
        problems = snap.verify_exports(text, public, a.run_id)
        if problems:
            raise FinalError("judging-final: the release does not match the judging section: " + "; ".join(problems[:8])
                             + ". Nothing changed")
        note = (f"exports checked against release `exports-{a.run_id}` (archive sha256 `{a.archive_sha256}`); the rows under "
                "`raw/` and `processed/` and the DuckDB table counts are carried over unchanged from the provisional snapshot, "
                "where they were verified, and were not re-hashed here.")
    else:
        snap.check_run(public, processed, a.run_id)
    old_rows = snap.section_rows(text)
    new_val, new_tour, v = plan(public, a.labels_dir, a.source)

    paths = {public / snap.VALIDATION: canonical_json(new_val), public / snap.JUDGE_TOUR: canonical_json(new_tour)}
    backup = {p: p.read_text(encoding="utf-8") for p in paths}
    try:
        for p, body in paths.items():
            write_text_atomic(p, body)
        if note:
            new_section = snap.build_exports_only(text, public, a.run_id, "final", note)
        else:
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
        if v.method == "records":
            rows = rc.read_records(a.labels_dir / rc.RECORDS_FILE)
            rc.write_section(a.validation_md, rc.render_section(rows, rows[0]["checked_on"]))
        else:
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
    what = "record-checked zombies, repaired again" if v.method == "records" else "labeled pairs, precision"
    print(f"judging-final: {v.n_paired} {what} {p.get('rate')} ({p.get('k')} of {p.get('n')}), "
          f"{len(v.confirmed)} confirmed ({v.method}); tour {new_tour['zombie_ids']}")
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
