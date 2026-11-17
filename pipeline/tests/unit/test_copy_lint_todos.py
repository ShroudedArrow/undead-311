"""REQ-WEB-COPY.2: copy-lint counts TODO-COPY markers in copy, not mentions of the marker in tests, the checker or the checklist."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("copy_lint", ROOT / "scripts" / "copy_lint.py")
copy_lint = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(copy_lint)  # type: ignore[union-attr]


def test_a_marker_in_copy_is_counted():
    assert copy_lint.count_todos("web/src/copy/en.json", '{"a": "TODO-COPY: write this"}') == 1
    assert copy_lint.count_todos("docs/METHODS.md", "TODO-COPY: a\nTODO-COPY: b") == 2


def test_tests_the_checker_and_the_checklist_are_not_counted():
    text = 'expect(x).not.toContain("TODO-COPY")'
    for rel in ("web/src/lib/a.test.ts", "web/src/pages/b.test.tsx", "web/src/lib/t.ts", "docs/PREFLIGHT.md"):
        assert copy_lint.count_todos(rel, text) == 0


def test_the_committed_tree_has_no_marker_left():
    """The Dec 2 freeze check (`--strict-todo`) passes on the tree."""
    assert _strict_total() == 0


def _strict_total() -> int:
    findings: list[str] = []
    return sum(copy_lint.lint_copy(p, findings) for p in copy_lint.files(copy_lint.COPY_GLOBS)) + sum(
        copy_lint.lint_code(p, findings) for p in copy_lint.files(copy_lint.CODE_GLOBS)
    )
