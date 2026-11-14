"""Contract check on the committed site data (REQ-OPS-CI.1, testing.md #16).

The files Netlify serves are the JSON files committed under web/public/data. Every one must validate against its
schema in /schemas/, and a file with no schema fails (review N2, ops#54). `cards/*.json` use card.schema.json.
Committed means tracked by git; outside a git checkout the folder is scanned instead. `make schema-check` runs this.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from undead311.export.writers import export_all

REPO = Path(__file__).resolve().parents[3]
DATA = Path("web/public/data")
# Internal run bookkeeping that is not a data contract, and placeholders.
NO_SCHEMA_NEEDED = {"stats/stats_status.json", ".gitkeep"}


def schema_name(rel: Path) -> str | None:
    """The schema a data file (relative to web/public/data) is checked against, or None when there is none.

    Stats files sit flat or under stats/ (the export has used both), so the folder is ignored for them."""
    if rel.parts[0] == "cards":
        return "card"
    name = rel.name.removesuffix(".json")
    return name if (REPO / "schemas" / f"{name}.schema.json").exists() else None


def data_files(root: Path = REPO, tracked_only: bool = True) -> list[Path]:
    """Paths relative to web/public/data. Tracked files when git can say; otherwise every file in the folder."""
    base = root / DATA
    if tracked_only:
        try:
            out = subprocess.run(["git", "ls-files", "-z", "--", str(DATA)], cwd=root, capture_output=True, check=True,
                                 text=True).stdout
            return sorted(Path(p).relative_to(DATA) for p in out.split("\0") if p)
        except (OSError, subprocess.CalledProcessError):
            pass
    return sorted(p.relative_to(base) for p in base.rglob("*") if p.is_file()) if base.exists() else []


def problems(files: list[Path], root: Path = REPO) -> list[str]:
    """One line per file that has no schema, is not JSON, or fails its schema."""
    found: list[str] = []
    for rel in files:
        if rel.as_posix() in NO_SCHEMA_NEEDED:
            continue
        name = schema_name(rel)
        if name is None:
            found.append(f"{rel}: no schema in /schemas/ for this file")
            continue
        schema = json.loads((REPO / "schemas" / f"{name}.schema.json").read_text())
        try:
            doc = json.loads((root / DATA / rel).read_text())
        except (OSError, ValueError) as e:
            found.append(f"{rel}: not readable JSON ({e})")
            continue
        errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
        found.extend(f"{rel}: {'/'.join(map(str, e.path)) or '<root>'}: {e.message[:120]}" for e in errors[:3])
    return found


def test_every_committed_web_data_file_validates_against_its_schema():
    """REQ-OPS-CI.1, testing.md #16: what Netlify serves matches the contract; a file with no schema fails."""
    bad = problems(data_files())
    assert not bad, "\n".join(bad[:20])


def test_the_exporter_output_is_checked_the_same_way(tmp_path):
    """REQ-OPS-CI.1: the helper accepts a real export, so the committed-data check is not only vacuously true."""
    from test_export import town_inputs

    result, cases, ctx = town_inputs()
    export_all(result, cases, tmp_path / DATA, ctx)
    files = data_files(tmp_path, tracked_only=False)
    assert files, "export wrote nothing"
    assert not problems(files, tmp_path)


def test_a_file_without_a_schema_fails(tmp_path):
    """REQ-OPS-CI.1 (review N2): the checker bites on an unknown file."""
    (tmp_path / DATA).mkdir(parents=True)
    (tmp_path / DATA / "mystery.json").write_text("{}")
    assert any("no schema" in p for p in problems([Path("mystery.json")], tmp_path))


def test_an_invalid_file_fails_and_a_card_shard_uses_the_card_schema(tmp_path):
    """REQ-OPS-CI.1 (review N2): a file missing required keys is reported; cards/* map to card.schema.json."""
    (tmp_path / DATA / "cards").mkdir(parents=True)
    (tmp_path / DATA / "cards" / "x-2020.json").write_text("{}")
    (tmp_path / DATA / "scorecard.json").write_text(json.dumps({"data_version": "v"}))
    assert schema_name(Path("cards/x-2020.json")) == "card"
    found = problems([Path("cards/x-2020.json"), Path("scorecard.json")], tmp_path)
    assert len(found) >= 2


@pytest.mark.parametrize("rel", ["stats/scorecard.json", "scorecard.json", "judge_tour.json"])
def test_stats_files_map_to_a_schema_whether_flat_or_in_stats(rel):
    """REQ-OPS-CI.1: the folder does not change which schema a stats file is checked against."""
    assert schema_name(Path(rel)) is not None
