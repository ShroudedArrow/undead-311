"""Nightly deep run really runs 10x: no property pins its own example count (REQ-OPS-PBT.1, ops#155; testing.md #19, #20, #16, #5).

`@settings(max_examples=N)` and fast-check's `{ numRuns: N }` override the profile or the global default, so a pinned
count would stay at 1x in the nightly run while the profile test (deep = 10 x fast) still passed."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "pipeline" / "tests"
SHIM = REPO / "ops" / "deep-pbt" / "fast-check.deep.mjs"
SELF = Path(__file__).resolve()


def pinned_counts(path: Path) -> list[tuple[int, str]]:
    """(line, source) of every `max_examples=` keyword whose value is not a call to `examples(...)`."""
    tree = ast.parse(path.read_text())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "max_examples":
                    ok = isinstance(kw.value, ast.Call) and getattr(kw.value.func, "id", "") == "examples"
                    if not ok:
                        bad.append((kw.value.lineno, ast.unparse(kw.value)))
    return bad


def test_no_property_pins_a_bare_example_count():
    """REQ-OPS-PBT.1: every `max_examples=` in a test is `examples(N)`; the profiles in conftest.py are the only bare numbers."""
    offenders = {}
    for path in sorted(TESTS.rglob("*.py")):
        if path.name == "conftest.py" or path == SELF:
            continue
        bad = pinned_counts(path)
        if bad:
            offenders[path.relative_to(REPO).as_posix()] = bad
    assert not offenders, f"pin counts with helpers.examples(N): {offenders}"


def test_the_checker_flags_a_bare_pinned_count(tmp_path):
    """REQ-OPS-PBT.1: the scan above would catch a regression (it is not vacuous)."""
    f = tmp_path / "t.py"
    f.write_text("@settings(max_examples=50)\ndef t(): ...\n@settings(max_examples=examples(50))\ndef u(): ...\n")
    assert pinned_counts(f) == [(1, "50")]


def run_count(profile: str | None, n: int) -> int:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "pipeline"), str(TESTS)])}
    env.pop("HYPOTHESIS_PROFILE", None)
    if profile:
        env["HYPOTHESIS_PROFILE"] = profile
    code = f"import conftest, helpers; print(helpers.examples({n}))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True, timeout=60)
    return int(out.stdout.strip())


def test_examples_is_n_under_fast_and_ten_n_under_deep():
    """REQ-OPS-PBT.1: the helper follows the active Hypothesis profile."""
    assert run_count(None, 25) == 25
    assert run_count("fast", 25) == 25
    assert run_count("deep", 25) == 250


@pytest.mark.skipif(shutil.which("node") is None or not (REPO / "web" / "node_modules" / "fast-check").is_dir(),
                    reason="needs node and web/node_modules")
def test_the_deep_fast_check_shim_scales_a_pinned_numruns_and_the_default():
    """REQ-OPS-PBT.1: `{ numRuns: 7 }` runs 70 times and a call without numRuns runs 1000 times (web contract properties, #16)."""
    script = (
        f'import fc from "{SHIM.as_posix()}";'
        "let a=0,b=0;"
        "fc.assert(fc.property(fc.integer(),()=>{a++;}),{numRuns:7});"
        "fc.assert(fc.property(fc.integer(),()=>{b++;}));"
        "console.log(a,b);"
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True, timeout=60)
    assert out.stdout.split() == ["70", "1000"]
