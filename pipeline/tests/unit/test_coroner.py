"""REQ-COR-1.1-1.4: templates, label precedence, unlabeled share, allowed set."""

from __future__ import annotations

import csv

import duckdb
import pytest

from undead311.coroner.join import (
    ALLOWED_LABELS,
    UnknownLabel,
    assign_label,
    join_labels,
    load_template_labels,
)
from undead311.coroner.templates import build_templates, mask_template


def make_con(rows):
    con = duckdb.connect()
    con.execute(
        "create table cases_clean(id varchar, system varchar, status varchar, closure_code varchar, "
        "closure_text varchar, coroner_label varchar)"
    )
    con.executemany("insert into cases_clean values (?,?,?,?,?,NULL)", rows)
    return con


def test_req_cor_1_1_mask_template_collapses_dates_numbers_and_case_ids():
    """REQ-COR-1.1: timestamps, dates, numbers and case IDs are masked; case and spacing are normalized."""
    a = mask_template("Case Closed. Closed date : 2026-05-01 08:57:13.83 Resolved  new cart 123 delv on 5/1/26")
    b = mask_template("Case Closed. Closed date : 2025-01-09 11:00:00.1 RESOLVED new cart 98 delv on 12/31/25")
    assert a == b == "case closed. resolved new cart <n> delv on <date>"
    assert mask_template("See new case BCS-00912002") == "see new case <case>"
    assert mask_template("") == "" and mask_template(None) == ""
    assert mask_template("Case Closed. Closed date : Fri Jan 02 10:11:12 EST 2015 Resolved") == "case closed. resolved"


def test_req_cor_1_1_templates_csv_is_deduplicated_sorted_with_an_example(tmp_path):
    """REQ-COR-1.1: coroner_templates.csv has template, n_cases, example_id, sorted by n_cases (open cases excluded)."""
    con = make_con([
        ("3", "legacy", "Closed", None, "Closed date : 2024-01-01 08:00:00 Case Resolved 5"),
        ("1", "legacy", "Closed", None, "Closed date : 2024-02-01 08:00:00 Case Resolved 9"),
        ("2", "legacy", "Closed", None, "Duplicate of Existing Case"),
        ("4", "legacy", "Open", None, "Closed date : 2024-02-01 08:00:00 Case Resolved 9"),
        ("5", "legacy", "Closed", None, None),
    ])  # fmt: skip
    path = build_templates(con, tmp_path)
    assert path.name == "coroner_templates.csv"
    rows = list(csv.DictReader(path.open()))
    assert rows == [
        {"template": "case resolved <n>", "n_cases": "2", "example_id": "1"},
        {"template": "duplicate of existing case", "n_cases": "1", "example_id": "2"},
    ]


def test_req_cor_1_2_precedence_transitioned_then_template_then_code():
    """REQ-COR-1.2: Transitioned -> referred even with a template label; template beats the code; Noted stays noted."""
    labels = {"resolved": "invalid", "tmpl": "made_safe_temporary"}
    assert assign_label("new", "Transitioned", "resolved", labels) == ("referred", False)
    assert assign_label("new", "Resolved", "tmpl", labels) == ("made_safe_temporary", False)
    assert assign_label("new", "Resolved successfully", "no template", labels) == ("resolved", False)
    assert assign_label("new", "Noted", "no template", labels) == ("noted", False)
    assert assign_label("legacy", None, "tmpl", labels) == ("made_safe_temporary", False)


def test_req_cor_1_3_unlabeled_closures_are_other_and_counted():
    """REQ-COR-1.3: no label -> other + unlabeled; the report shows the covered share."""
    con = make_con([
        ("1", "legacy", "Closed", None, "Case Resolved"),
        ("2", "legacy", "Closed", None, "Something odd"),
        ("3", "new", "Closed", "Resolved", None),
        ("4", "new", "Closed", None, None),
        ("5", "legacy", "Open", None, None),
    ])  # fmt: skip
    con.execute("create table x(template varchar, label varchar)")
    path = None
    report = join_labels(con, path)
    got = dict(con.execute("select id, coroner_label from cases_clean").fetchall())
    assert got == {"1": "other", "2": "other", "3": "resolved", "4": "other", "5": None}
    assert report.closed_in_scope == 4 and report.unlabeled == 3
    assert report.labels_file_missing is True
    assert report.covered_share == pytest.approx(0.25)


def test_req_cor_1_2_join_uses_the_label_file(tmp_path):
    """REQ-COR-1.2: labels are joined by masked template."""
    f = tmp_path / "coroner_labels.csv"
    f.write_text("template,label\ncase resolved <n>,resolved\nduplicate of existing case,duplicate\n")
    con = make_con([
        ("1", "legacy", "Closed", None, "Case Resolved 77"),
        ("2", "legacy", "Closed", None, "DUPLICATE of existing case"),
    ])
    report = join_labels(con, f)
    assert dict(con.execute("select id, coroner_label from cases_clean").fetchall()) == {"1": "resolved", "2": "duplicate"}
    assert report.unlabeled == 0 and report.labels_file_missing is False


def test_req_cor_1_4_label_outside_the_allowed_set_is_rejected(tmp_path):
    """REQ-COR-1.4: an unknown label in the label file raises."""
    f = tmp_path / "bad.csv"
    f.write_text("template,label\nfoo,zombie\n")
    with pytest.raises(UnknownLabel):
        load_template_labels(f)
    assert set(ALLOWED_LABELS) == {
        "resolved", "noted", "invalid", "duplicate", "referred", "made_safe_temporary", "planned_followup",
        "bulk_backlog", "other",
    }  # fmt: skip
