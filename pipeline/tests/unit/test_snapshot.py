"""Frozen judging snapshot (REQ-OPS-SNAP.1, REQ-OPS-SNAP.2) and check O4: the same input gives the same hashes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import examples
from hypothesis import given, settings
from hypothesis import strategies as st

from undead311 import snapshot as snap

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "pipeline" / "scripts" / "snapshot.py"

_spec = importlib.util.spec_from_file_location("download_script", REPO / "pipeline" / "scripts" / "download.py")
download = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download)


def make_tree(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


@pytest.fixture
def site(tmp_path):
    public, processed = tmp_path / "public", tmp_path / "processed"
    make_tree(public, {"status.json": json.dumps({"ok": True, "data_end": "2026-11-11"}).encode(),
                       "zombies.json": b"[1,2]", "cards/a.json": b"{}"})
    make_tree(processed, {"cases.parquet": b"PAR1", "run_report.json": b"{}", "undead311.duckdb": b"db", "notes.txt": b"x"})
    return public, processed


def rows(public, processed):
    return snap.collect(public, processed)


def test_collect_lists_served_files_and_processed_parquet_but_not_the_duckdb_file(site):
    """REQ-OPS-SNAP.1: served data and processed Parquet, sorted; the DuckDB file and stray files are left out."""
    labels = [r[0] for r in rows(*site)]
    assert labels == sorted(labels)
    assert "web/public/data/cards/a.json" in labels and "processed/cases.parquet" in labels
    assert "processed/run_report.json" in labels
    assert not any("duckdb" in x or "notes" in x for x in labels)


def test_hashes_are_the_sha256_of_the_bytes(site):
    """REQ-OPS-SNAP.1."""
    by = {r[0]: r for r in rows(*site)}
    _label, size, digest = by["web/public/data/zombies.json"]
    assert (size, digest) == (5, hashlib.sha256(b"[1,2]").hexdigest())


def test_same_input_gives_the_same_section_even_in_another_folder(site, tmp_path):
    """REQ-OPS-SNAP.1 (check O4): no path, clock or mtime goes into the section."""
    public, processed = site
    first = snap.build(public, processed, None, None)
    other = tmp_path / "elsewhere"
    make_tree(other / "p", {f.relative_to(public).as_posix(): f.read_bytes() for f in public.rglob("*") if f.is_file()})
    make_tree(other / "q", {f.relative_to(processed).as_posix(): f.read_bytes() for f in processed.rglob("*") if f.is_file()})
    for f in other.rglob("*"):
        if f.is_file():
            os.utime(f, (1, 1))
    assert snap.build(other / "p", other / "q", None, None) == first


@settings(max_examples=examples(40), deadline=None)
@given(st.dictionaries(st.text("abcdef", min_size=1, max_size=6), st.binary(max_size=20), min_size=1, max_size=6), st.randoms(use_true_random=False))
def test_the_section_does_not_depend_on_write_order_and_changes_with_any_byte(tmp_path_factory, files, rnd):
    """REQ-OPS-SNAP.1 (check O4): order-independent, and one changed byte changes the combined hash."""
    a, b = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    items = [(f"{k}.json", v) for k, v in files.items()]
    make_tree(a, dict(items))
    rnd.shuffle(items)
    make_tree(b, dict(items))
    assert snap.collect(a, None) == snap.collect(b, None)
    name, data = items[0]
    (b / name).write_bytes(data + b"!")
    assert snap.combined_hash(snap.collect(a, None)) != snap.combined_hash(snap.collect(b, None))


def test_the_section_names_the_data_end_the_tag_and_the_owner_steps(site):
    """REQ-OPS-SNAP.1: data end from status.json, default tag judged-<date>, tag commands for the owner."""
    section = snap.build(*site, None, None)
    assert "Data through: 2026-11-11" in section and "`judged-2026-11-11`" in section
    assert "git tag -a judged-2026-11-11" in section and "git push origin judged-2026-11-11" in section
    assert "JUDGED_TAG" in section
    assert snap.build(*site, "2026-11-11", "judged-final").count("judged-final") >= 3


def test_upsert_replaces_the_section_keeps_the_download_table_and_is_idempotent(site):
    """REQ-OPS-SNAP.1: the table above the section is untouched; a second run changes nothing."""
    table = "# Data snapshot\n\n| file | x |\n|---|---|\n| a.csv | 1 |\n"
    section = snap.build(*site, None, None)
    once = snap.upsert_section(table, section)
    assert once.startswith(table.rstrip("\n")) and once.count(snap.BEGIN) == 1
    assert snap.upsert_section(once, section) == once
    (site[0] / "status.json").write_text(json.dumps({"ok": True, "data_end": "2027-01-01"}))   # the data now runs further
    changed = snap.build(*site, "2027-01-01", None)
    twice = snap.upsert_section(once, changed)
    assert twice.count(snap.BEGIN) == 1 and "2027-01-01" in twice and "2026-11-11" not in twice
    assert twice.startswith(table.rstrip("\n"))


def test_a_download_keeps_the_judging_section(site, tmp_path):
    """REQ-OPS-SNAP.1: rewriting the download table or its geography rows never erases the judging section."""
    section = snap.build(*site, None, None)
    path = tmp_path / "SNAPSHOT.md"
    path.write_text(snap.upsert_section("# Data snapshot\n\n| file | resource | last_modified | bytes | sha256 |\n|---|---|---|---|---|\n| 311_2015.csv | r | t | 1 | h |\n", section))
    download.write_snapshot(path, "# Data snapshot\n\nDownloaded: 2026-12-01\n\n| file | resource | last_modified | bytes | sha256 |\n|---|---|---|---|---|\n| 311_2016.csv | r | t | 2 | h |\n")
    text = path.read_text()
    assert snap.extract_section(text) == section and "311_2016.csv" in text and "311_2015.csv" not in text
    assert text.index("311_2016.csv") < text.index(snap.BEGIN)
    geo = download.upsert_geo_rows(text, [("street_segments_sam.geojson", "GeoJSON", "t", 3, "h")])
    assert snap.extract_section(geo) == section
    assert geo.index("street_segments_sam.geojson") < geo.index(snap.BEGIN)


def test_the_real_snapshot_file_still_has_its_download_table():
    """REQ-OPS-SNAP.1: data/SNAPSHOT.md keeps the raw-download rows (the judging section is added by `make snapshot`)."""
    text = (REPO / "data" / "SNAPSHOT.md").read_text()
    assert "| file | resource | last_modified | bytes | sha256 |" in text and "311_new_system.csv" in text


def run_cli(tmp_path, public, processed, *extra):
    snapshot = tmp_path / "SNAPSHOT.md"
    env = {**os.environ, "PYTHONPATH": str(REPO / "pipeline")}
    r = subprocess.run([sys.executable, str(SCRIPT), "--public", str(public), "--processed", str(processed),
                        "--snapshot", str(snapshot), *extra], capture_output=True, text=True, check=False, env=env, timeout=120)
    return r, snapshot


def test_cli_writes_then_checks_then_detects_a_changed_file(site, tmp_path):
    """REQ-OPS-SNAP.1, REQ-OPS-SNAP.2: write the section; --check passes; a changed served file fails the check."""
    public, processed = site
    r, snapshot = run_cli(tmp_path, public, processed)
    assert r.returncode == 0, r.stderr
    assert "git tag -a judged-2026-11-11" in r.stdout   # prints the commands, does not run them
    first = snapshot.read_text()
    r, _ = run_cli(tmp_path, public, processed)
    assert snapshot.read_text() == first                                             # same input, same file
    assert run_cli(tmp_path, public, processed, "--check")[0].returncode == 0
    (public / "zombies.json").write_bytes(b"[1,2,3]")
    assert run_cli(tmp_path, public, processed, "--check")[0].returncode == 1


def test_cli_never_creates_a_git_tag(site, tmp_path):
    """REQ-OPS-SNAP.1: tagging is the owner's step. The script holds no git call."""
    assert "subprocess" not in SCRIPT.read_text() and "git tag" in (REPO / "pipeline" / "undead311" / "snapshot.py").read_text()
    assert "subprocess" not in (REPO / "pipeline" / "undead311" / "snapshot.py").read_text()


def test_cli_without_status_or_data_end_stops_with_a_message(tmp_path):
    """REQ-OPS-SNAP.1: no pipeline output yet means a clear stop, not an empty snapshot."""
    r, snapshot = run_cli(tmp_path, tmp_path / "none", tmp_path / "none2")
    assert r.returncode != 0 and "make pipeline" in r.stderr and not snapshot.exists()


def test_make_snapshot_is_wired_to_the_script():
    """REQ-OPS-SNAP.1: `make snapshot` and `make snapshot-check` run the script (no longer a stub)."""
    mk = (REPO / "Makefile").read_text()
    assert "pipeline/scripts/snapshot.py\n" in mk and "pipeline/scripts/snapshot.py --check" in mk
    assert "snapshot:\n\t$(STUB)" not in mk


# ---- judge mode stays on the frozen snapshot (REQ-OPS-SNAP.2, ops#157) --------------------------------------------------

def judge_site(tmp_path):
    """A served-data folder with a tour of two zombies in two card shards, and the snapshot text that describes it."""
    public = tmp_path / "public"
    points = {"id": ["z1", "z2", "z3"], "neighborhood": ["Back Bay", "South End", "Back Bay"], "year": [2025, 2026, 2025]}
    make_tree(public, {"status.json": json.dumps({"ok": True, "data_end": "2026-11-11"}).encode(),
                       "points.json": json.dumps(points).encode(),
                       "stats/judge_tour.json": json.dumps({"zombie_ids": ["z1", "z2"]}).encode(),
                       "cards/back-bay-2025.json": b'{"cards": ["z1", "z3"]}', "cards/south-end-2026.json": b'{"cards": ["z2"]}',
                       "cards/other-2025.json": b"{}", "zombies.json": b"[]"})
    return public, snap.render_section(snap.collect(public, None), "2026-11-11", "judged-2026-11-11")


def test_freeze_copies_the_tour_the_points_and_the_tour_shards_only(tmp_path):
    """REQ-OPS-SNAP.2: judge mode's files, and nothing else, go to frozen/ with the same layout."""
    public, text = judge_site(tmp_path)
    copied = snap.freeze_judge(public, text)
    assert copied == ["cards/back-bay-2025.json", "cards/south-end-2026.json", "points.json", "stats/judge_tour.json"]
    assert sorted(p.relative_to(public / "frozen").as_posix() for p in (public / "frozen").rglob("*") if p.is_file()) == copied
    assert snap.check_frozen(public, text) == []


def test_frozen_files_survive_a_pipeline_run_that_rewrites_the_live_ones(tmp_path):
    """REQ-OPS-SNAP.2 (ops#157): after the nightly pipeline overwrites the live files, the frozen copies still equal the
    tagged ones, byte for byte, and the check on the built site passes; a changed frozen file fails it."""
    public, text = judge_site(tmp_path)
    tagged = {p.relative_to(public).as_posix(): p.read_bytes() for p in public.rglob("*") if p.is_file()}
    snap.freeze_judge(public, text)
    (public / "stats" / "judge_tour.json").write_text(json.dumps({"zombie_ids": ["z3"]}))   # the pipeline's rewrite
    (public / "points.json").write_text("{}")
    (public / "cards" / "back-bay-2025.json").write_text('{"cards": ["z1", "z3", "new"]}')
    for rel in ("stats/judge_tour.json", "points.json", "cards/back-bay-2025.json", "cards/south-end-2026.json"):
        assert (public / "frozen" / rel).read_bytes() == tagged[rel]
    assert snap.check_frozen(public, text) == []
    (public / "frozen" / "points.json").write_text("{}")
    assert snap.check_frozen(public, text) == ["points.json differs from the judging section"]


def test_the_table_ignores_the_frozen_folder(tmp_path):
    """REQ-OPS-SNAP.1, REQ-OPS-SNAP.2: freezing does not change the hashes of `make snapshot` (a second run stays equal)."""
    public, text = judge_site(tmp_path)
    before = snap.collect(public, None)
    snap.freeze_judge(public, text)
    assert snap.collect(public, None) == before


def test_freeze_refuses_files_that_do_not_match_the_table(tmp_path):
    """REQ-OPS-SNAP.2: a tag whose files differ from data/SNAPSHOT.md, or a missing section, stops the nightly."""
    public, text = judge_site(tmp_path)
    (public / "points.json").write_text('{"id": ["z1", "z2"], "neighborhood": ["Back Bay", "South End"], "year": [2025, 2026]}')
    with pytest.raises(SystemExit, match="points.json does not match"):
        snap.freeze_judge(public, text)
    with pytest.raises(SystemExit, match="no judging section"):
        snap.freeze_judge(public, "# SNAPSHOT\n")
    assert not (public / "frozen" / "stats").exists() or not any((public / "frozen" / "stats").iterdir())


def test_check_frozen_reports_a_missing_folder_a_missing_section_and_an_unlisted_file(tmp_path):
    """REQ-OPS-SNAP.2: the verify step fails when there is nothing, or something the table does not list, to ship."""
    public, text = judge_site(tmp_path)
    assert snap.check_frozen(public, text) == [f"{public / 'frozen'} is missing or empty"]
    snap.freeze_judge(public, text)
    assert snap.check_frozen(public, "") == ["data/SNAPSHOT.md has no judging section"]
    (public / "frozen" / "extra.json").write_text("{}")
    assert snap.check_frozen(public, text) == ["extra.json has no row in the judging section"]


def test_the_exporter_never_touches_the_frozen_folder():
    """REQ-OPS-SNAP.2: the pipeline's swap removes only files it owns, and frozen/ is not one of them."""
    from undead311.pipeline import owns_output

    for rel in ("frozen/stats/judge_tour.json", "frozen/points.json", "frozen/cards/back-bay-2025.json", "frozen/points.json.gz"):
        assert not owns_output(rel), rel
    assert owns_output("cards/back-bay-2025.json") and owns_output("zombies.json")


def test_the_shard_slug_matches_the_exporter_and_the_web_rule():
    """REQ-OPS-SNAP.2: frozen shard names follow `export.writers.slug` (and web/src/lib/shard.ts uses the same regex)."""
    from undead311.export.writers import slug

    for name in ("Back Bay", "South Boston / Seaport", "Allston-Brighton", None, "", "Jamaica Plain!"):
        assert snap.slug(name) == slug(name)
    assert 'replace(/[^a-z0-9]+/g, "-")' in (REPO / "web" / "src" / "lib" / "shard.ts").read_text()


def test_the_cli_freezes_and_checks_the_frozen_copy(tmp_path):
    """REQ-OPS-SNAP.2: `--freeze-judge` then `--check-frozen` (what the workflow runs), and a stale copy fails the check."""
    public, text = judge_site(tmp_path)
    snapshot = tmp_path / "SNAPSHOT.md"
    snapshot.write_text(text)
    r, _ = run_cli(tmp_path, public, tmp_path / "none", "--freeze-judge")
    assert r.returncode == 0, r.stderr
    assert run_cli(tmp_path, public, tmp_path / "none", "--check-frozen")[0].returncode == 0
    (public / "frozen" / "stats" / "judge_tour.json").write_text("{}")
    r, _ = run_cli(tmp_path, public, tmp_path / "none", "--check-frozen")
    assert r.returncode == 1 and "judge_tour.json differs" in r.stderr


def test_snapshot_refuses_a_data_end_the_files_do_not_run_through(site, tmp_path):
    """REQ-OPS-SNAP.1 (ops#160): `--data-end` must equal status.json's data_end; the same date is accepted."""
    public, processed = site
    r, snapshot = run_cli(tmp_path, public, processed, "--data-end", "2026-12-31")
    assert r.returncode == 1 and "2026-11-11" in (r.stderr + r.stdout) and not snapshot.exists()
    r, snapshot = run_cli(tmp_path, public, processed, "--data-end", "2026-11-11")
    assert r.returncode == 0 and "Data through: 2026-11-11" in snapshot.read_text()


def test_data_end_flag_fills_in_a_status_that_has_no_date(tmp_path):
    """REQ-OPS-SNAP.1: with no data_end in status.json the flag is still the way to name the date."""
    public = tmp_path / "public"
    make_tree(public, {"status.json": b'{"ok": true}', "zombies.json": b"[]"})
    assert "Data through: 2026-11-11" in snap.build(public, None, "2026-11-11", None)


def test_the_nightly_deploy_never_replaces_the_frozen_data_with_a_failed_run():
    """REQ-OPS-SNAP.2: a failed or disabled refresh leaves the last good deploy (and so the snapshot) live."""
    nightly = (REPO / "ops" / "undead-311-data" / ".github" / "workflows" / "nightly.yml").read_text()
    assert "status_history.py check" in nightly and nightly.index("status_history.py check") < nightly.index("netlify-cli@")
    assert "last good deploy" in nightly
