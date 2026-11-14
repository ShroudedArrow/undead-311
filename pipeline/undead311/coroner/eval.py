"""Coroner accuracy against the owner's hand labels (REQ-COR-EVAL.1-2).

`data/labels/coroner_hand_labels.csv` is human input: one row per hand-labelled closure template, with the column
`template` (the masked text used as the key in `coroner_labels.csv`) or `closure_text` (raw text, masked here), and the
column `hand_label` (or `label`). Each row is compared with the label table's label for the same template; a template
the table does not list counts as `other` (the label the pipeline gives an unlabeled closure) and is counted separately.
The result (accuracy, a Wilson 95% interval, the top confusions) goes into a marked block of `docs/VALIDATION.md`.
A missing hand-label file is not an error: it is human input, so the command says so and exits 0.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from undead311.coroner.join import check_label, load_template_labels
from undead311.coroner.templates import mask_template
from undead311.stats.intervals import wilson

START = "<!-- coroner-eval:start -->"
END = "<!-- coroner-eval:end -->"
TOP_CONFUSIONS = 10
HAND_LABELS_FILE = "coroner_hand_labels.csv"
LABELS_FILE = "coroner_labels.csv"


@dataclass(frozen=True)
class EvalReport:
    n: int
    correct: int
    unlisted: int  # hand-labelled templates that the label table does not list (predicted `other`)
    confusions: tuple[tuple[str, str, int], ...] = field(default_factory=tuple)  # (hand label, table label, count)

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.n if self.n else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.correct, self.n)


def read_hand_labels(path: Path) -> list[tuple[str, str]]:
    """(template, hand label) per row; an unknown label raises UnknownLabel, a row with no text is skipped."""
    out = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            text = row.get("template") or mask_template(row.get("closure_text"))
            label = (row.get("hand_label") or row.get("label") or "").strip()
            if text and label:
                out.append((text.strip(), check_label(label)))
    return out


def evaluate(labels: dict[str, str], hand: list[tuple[str, str]]) -> EvalReport:
    """Compare the label table with the hand labels (REQ-COR-EVAL.1). Pure: no files."""
    wrong: Counter[tuple[str, str]] = Counter()
    correct = unlisted = 0
    for template, truth in hand:
        if template not in labels:
            unlisted += 1
        got = labels.get(template, "other")
        if got == truth:
            correct += 1
        else:
            wrong[(truth, got)] += 1
    top = sorted(wrong.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_CONFUSIONS]
    return EvalReport(len(hand), correct, unlisted, tuple((t, g, n) for (t, g), n in top))


def render_section(r: EvalReport, hand_file: str = f"data/labels/{HAND_LABELS_FILE}") -> str:
    """The marked markdown block written to docs/VALIDATION.md. Contains no date, so a rerun gives the same bytes."""
    lines = [START, "## Coroner accuracy", ""]
    if not r.n:
        lines += [f"`{hand_file}` has no usable rows, so there is no accuracy to report.", END]
        return "\n".join(lines) + "\n"
    lo, hi = r.interval  # type: ignore[misc]
    lines += [
        f"Label table compared with {r.n} hand-labelled closure templates (`{hand_file}`).",
        "",
        f"- Accuracy: {r.accuracy:.1%} ({r.correct} of {r.n}), Wilson 95% interval {lo:.1%} to {hi:.1%}.",
        f"- Hand-labelled templates the label table does not list (counted as `other`): {r.unlisted}.",
        "",
    ]
    if r.confusions:
        lines += ["Top confusions (hand label, table label, templates):", ""]
        lines += ["| hand label | table label | templates |", "|---|---|---|"]
        lines += [f"| {t} | {g} | {n} |" for t, g, n in r.confusions]
    else:
        lines += ["No confusions: every hand label agrees with the label table."]
    lines += [END]
    return "\n".join(lines) + "\n"


def write_section(validation_md: Path, section: str) -> None:
    """Replace the marked block in `validation_md` (or append it); the rest of the file is untouched."""
    p = Path(validation_md)
    text = p.read_text(encoding="utf-8") if p.is_file() else "# Validation\n"
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    new = pattern.sub(lambda _m: section, text) if pattern.search(text) else text.rstrip("\n") + "\n\n" + section
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8")


def run(labels_dir: Path, validation_md: Path) -> tuple[int, str]:
    """`make coroner-eval`: (exit code, message). A missing hand-label file gives (0, message) and writes nothing."""
    hand_path = Path(labels_dir) / HAND_LABELS_FILE
    if not hand_path.is_file():
        return 0, (
            f"coroner-eval: {hand_path} is missing. The hand labels are human input; nothing to evaluate "
            "(REQ-COR-EVAL.2)."
        )
    report = evaluate(load_template_labels(Path(labels_dir) / LABELS_FILE), read_hand_labels(hand_path))
    write_section(validation_md, render_section(report))
    if not report.n:
        return 0, f"coroner-eval: {hand_path} has no usable rows"
    lo, hi = report.interval  # type: ignore[misc]
    return 0, f"coroner-eval: accuracy {report.accuracy:.1%} ({report.correct}/{report.n}), 95% CI {lo:.1%} to {hi:.1%}"
