"""Property P11 (testing.md #16): every exported file validates; an invalid record is refused before writing."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import examples
from hypothesis import given, settings
from hypothesis import strategies as st
from strategies import town

from undead311.detect.core import detect
from undead311.export.writers import ContractError, ExportContext, export_all, load_schema, validate

CTX = ExportContext(data_version="2026-11-12+abc+def", run_time="2026-11-13T00:00:00Z")


@settings(max_examples=examples(40))
@given(town())
def test_prop_p11_every_exported_file_validates_against_its_schema(cases):
    """REQ-EXP-1.1: exports of any generated town validate, and a re-run gives identical bytes (REQ-EXP-1.3)."""
    result = detect(cases)
    by_id = {c.id: c for c in cases}
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        for folder in (a, b):
            for path in (p for p in export_all(result, by_id, Path(folder), CTX) if p.suffix == ".json"):
                payload = json.loads(path.read_text())
                name = "card" if path.parent.name == "cards" else path.stem
                validate(name, payload)
        assert {p.name: p.read_bytes() for p in Path(a).rglob("*.json")} == {
            p.name: p.read_bytes() for p in Path(b).rglob("*.json")
        }


@settings(max_examples=examples(40))
@given(town(), st.sampled_from(["confidence", "tier", "match_mode", "reports_after"]))
def test_prop_p11_an_invalid_record_is_refused_before_anything_is_written(cases, field):
    """REQ-EXP-1.1: one bad value (out of range or not in the enum) stops the export with nothing written."""
    result = detect(cases)
    if not result.zombies:
        return
    bad = {"confidence": 2.0, "tier": "maybe", "match_mode": "guess", "reports_after": 0}[field]
    result.zombies[0] = replace(result.zombies[0], **{field: bad})
    with tempfile.TemporaryDirectory() as folder:
        with pytest.raises(ContractError):
            export_all(result, {c.id: c for c in cases}, Path(folder), CTX)
        assert list(Path(folder).iterdir()) == []


def test_prop_p11_every_engine_schema_requires_data_version():
    """REQ-EXP-1.2: files carry data_version (the schemas require it)."""
    for name in ("zombies", "incidents", "points", "card", "exclusions", "separate_deaths", "repeat_offenders",
                 "bulk_closures", "status"):  # fmt: skip
        assert "data_version" in load_schema(name)["required"]
