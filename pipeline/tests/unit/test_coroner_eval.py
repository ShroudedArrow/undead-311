"""REQ-COR-EVAL.1-2: Coroner accuracy against hand labels, the Wilson interval, the confusions and the VALIDATION.md block."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from undead311.cli import main
from undead311.coroner.eval import (
    END,
    START,
    evaluate,
    read_hand_labels,
    render_section,
    run,
    write_section,
)
from undead311.coroner.join import ALLOWED_LABELS, UnknownLabel
from undead311.stats.intervals import wilson


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_req_cor_eval_1_accuracy_interval_and_top_confusions():
    labels = {"a": "resolved", "b": "referred", "c": "invalid", "d": "resolved"}
    hand = [("a", "resolved"), ("b", "resolved"), ("c", "duplicate"), ("d", "duplicate"), ("zzz", "other"), ("y", "noted")]
    r = evaluate(labels, hand)
    assert (r.n, r.correct, r.unlisted) == (6, 2, 2)  # a, and zzz (unlisted -> other == other)
    assert r.accuracy == pytest.approx(2 / 6) and r.interval == wilson(2, 6)
    assert r.confusions == (("duplicate", "invalid", 1), ("duplicate", "resolved", 1), ("noted", "other", 1),
                            ("resolved", "referred", 1))  # fmt: skip


def test_req_cor_eval_1_confusions_are_sorted_by_count_then_name_and_capped():
    labels = {f"t{i}": "resolved" for i in range(30)}
    hand = [(f"t{i}", "noted") for i in range(12)] + [(f"t{i}", "invalid") for i in range(12, 15)]
    r = evaluate(labels, hand)
    assert r.confusions[0] == ("noted", "resolved", 12) and r.confusions[1] == ("invalid", "resolved", 3)
    many = evaluate({f"t{i}": "resolved" for i in range(30)}, [(f"t{i}", ALLOWED_LABELS[1 + i % 8]) for i in range(30)])
    assert len(many.confusions) <= 10


def test_req_cor_eval_1_hand_label_file_accepts_template_or_raw_text_and_rejects_unknown_labels(tmp_path):
    f = write(tmp_path / "h.csv", "template,hand_label\ncase closed. case resolved,resolved\n")
    assert read_hand_labels(f) == [("case closed. case resolved", "resolved")]
    g = write(tmp_path / "g.csv", "closure_text,label\nCase Closed. Case Resolved 2024-01-02,resolved\n")
    assert read_hand_labels(g)[0][1] == "resolved"
    bad = write(tmp_path / "b.csv", "template,hand_label\nx,zombie\n")
    with pytest.raises(UnknownLabel):
        read_hand_labels(bad)
    assert read_hand_labels(write(tmp_path / "e.csv", "template,hand_label\n,resolved\nx,\n")) == []


def test_req_cor_eval_1_section_replaces_its_own_block_and_keeps_the_rest(tmp_path):
    md = write(tmp_path / "VALIDATION.md", "# Validation\n\nField sample text.\n")
    r1 = evaluate({"a": "resolved"}, [("a", "resolved")])
    write_section(md, render_section(r1))
    write_section(md, render_section(evaluate({"a": "resolved"}, [("a", "noted")])))
    text = md.read_text()
    assert text.count(START) == 1 and text.count(END) == 1 and "Field sample text." in text
    assert "0.0%" in text and "Top confusions" in text and "| noted | resolved | 1 |" in text


def test_req_cor_eval_2_a_missing_hand_label_file_says_so_and_exits_zero(tmp_path, capsys):
    md = tmp_path / "VALIDATION.md"
    code, message = run(tmp_path, md)
    # owner decision 2026-11-16: there is no hand-label set; the random draw is the evaluation set, and without it nothing is written
    assert code == 0 and "missing" in message and "coroner_random200.csv is the evaluation set" in message and not md.exists()
    write(tmp_path / "coroner_labels.csv", "template,label\na,resolved\n")
    assert main(["coroner-eval", "--labels-dir", str(tmp_path), "--validation", str(md)]) == 0
    assert "missing" in capsys.readouterr().out and not md.exists()


def test_req_cor_eval_1_cli_writes_the_report(tmp_path, capsys):
    write(tmp_path / "coroner_labels.csv", "template,label\na,resolved\nb,referred\n")
    write(tmp_path / "coroner_hand_labels.csv", "template,hand_label\na,resolved\nb,resolved\n")
    md = tmp_path / "VALIDATION.md"
    assert main(["coroner-eval", "--labels-dir", str(tmp_path), "--validation", str(md)]) == 0
    assert "accuracy 50.0% (1/2)" in capsys.readouterr().out
    assert "| resolved | referred | 1 |" in md.read_text()


def test_req_cor_eval_1_an_empty_hand_label_file_writes_no_accuracy(tmp_path):
    write(tmp_path / "coroner_labels.csv", "template,label\na,resolved\n")
    write(tmp_path / "coroner_hand_labels.csv", "template,hand_label\n")
    md = tmp_path / "V.md"
    code, message = run(tmp_path, md)
    assert code == 0 and "no usable rows" in message and "no accuracy" in md.read_text()


label = st.sampled_from(ALLOWED_LABELS)


@given(st.dictionaries(st.text("abc", min_size=1, max_size=3), label, max_size=8),
       st.lists(st.tuples(st.text("abc", min_size=1, max_size=3), label), max_size=30))
def test_req_cor_eval_1_accuracy_is_a_rate_inside_its_interval_and_counts_add_up(table, hand):
    r = evaluate(table, hand)
    assert r.n == len(hand) and 0 <= r.correct <= r.n
    assert sum(n for *_, n in r.confusions) <= r.n - r.correct
    if r.n:
        lo, hi = r.interval
        assert 0 <= lo <= r.accuracy <= hi <= 1
    else:
        assert r.accuracy is None and r.interval is None
    assert evaluate(table, list(reversed(hand))) == r  # row order does not matter
