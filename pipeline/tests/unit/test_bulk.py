"""REQ-BULK.1-2 (ZD step 10): bulk-closure groups, the separate flag, and the exported file."""

from __future__ import annotations

import json
import random
from dataclasses import replace
from datetime import datetime, timedelta

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from undead311.detect.bulk import bulk_closures, flag_cases
from undead311.detect.params import DEFAULT
from undead311.export.writers import validate

TEXT = "Case Closed. Closed date : 2024-05-01 10:00:00 Case Resolved"
OTHER = "Case Noted. Closed date : 2024-05-01 10:00:00 No action"


def table(rows) -> duckdb.DuckDBPyConnection:
    """rows: (id, department, close datetime in UTC, closure_text)."""
    con = duckdb.connect()
    con.execute("create table cases_clean(id varchar, system varchar, department varchar, status varchar, "
                "close_time_utc timestamp, closure_text varchar, scope_tier varchar, coroner_label varchar)")  # fmt: skip
    if rows:
        con.executemany("insert into cases_clean values (?,?,?,?,?,?,?,?)",
                        [(i, "legacy", d, "Closed", c, t, "core", "resolved") for i, d, c, t in rows])  # fmt: skip
    return con


def day(n: int, hour: int = 15) -> datetime:
    return datetime(2024, 1, 1, hour) + timedelta(days=n)


def steady_plus_spike(spike: int, steady_days: int = 10, per_day: int = 3, dept="PWDx", text=TEXT):
    rows = [(f"s{d}-{k}", dept, day(d), text) for d in range(steady_days) for k in range(per_day)]
    rows += [(f"b{k}", dept, day(steady_days + 1), text) for k in range(spike)]
    return rows


def test_req_bulk_1_a_spike_of_50_and_ten_times_usual_is_flagged_with_its_numbers():
    con = table(steady_plus_spike(60))
    [g] = bulk_closures(con)
    assert (g.department, g.close_date, g.n_cases) == ("PWDx", "2024-01-12", 60)
    assert g.usual_daily == 3 and g.ratio == 20  # median of ten days of 3 and one day of 60
    validate("bulk_closures", {"data_version": "v", "bulk_closures": [g.to_json()]})
    assert g.template == "case closed. case resolved"


def test_req_bulk_1_both_thresholds_are_inclusive_and_both_are_needed():
    assert len(bulk_closures(table(steady_plus_spike(50, per_day=5)))) == 1  # exactly 50 and exactly 10 times
    assert not bulk_closures(table(steady_plus_spike(49, per_day=1)))  # many times usual, but 49 < 50 cases
    assert not bulk_closures(table(steady_plus_spike(50, per_day=6)))  # 50 cases, but only 8.3 times usual
    assert not bulk_closures(table(steady_plus_spike(0)))


def test_req_bulk_1_usual_count_is_per_department_and_template():
    """The same 60 closures are usual for a department that does this daily, and bulk for one that does not."""
    heavy = [(f"h{d}-{k}", "BIG", day(d), TEXT) for d in range(10) for k in range(60)]
    quiet = steady_plus_spike(60, dept="SMALL")
    flagged = bulk_closures(table(heavy + quiet))
    assert [(g.department, g.close_date) for g in flagged] == [("SMALL", "2024-01-12")]
    other_template = [(f"t{k}", "PWDx", day(11), OTHER) for k in range(60)]  # same day, a template with no history
    groups = bulk_closures(table(steady_plus_spike(0) + other_template))
    assert groups == [] or groups[0].usual_daily == 60  # its only day is its own median: never 10x


def test_req_bulk_1_close_date_is_the_boston_local_date():
    """23:30 on 2024-07-01 in Boston is 03:30 UTC on 07-02, so the group belongs to 07-01."""
    rows = [(f"a{k}", "PWDx", datetime(2024, 7, 2, 3, 30), TEXT) for k in range(60)]
    rows += [(f"s{d}-0", "PWDx", datetime(2024, 6, 1 + d, 15), TEXT) for d in range(10)]
    [g] = bulk_closures(table(rows))
    assert g.close_date == "2024-07-01"


def test_req_bulk_2_the_flag_is_separate_and_never_overwrites_the_label():
    con = table(steady_plus_spike(60))
    before = con.execute("select id, coroner_label from cases_clean order by id").fetchall()
    n = flag_cases(con, bulk_closures(con))
    assert n == 60
    assert con.execute("select id, coroner_label from cases_clean order by id").fetchall() == before
    assert con.execute("select count(*) from cases_clean where bulk_closure and id like 'b%'").fetchone()[0] == 60
    assert con.execute("select count(*) from cases_clean where bulk_closure and id like 's%'").fetchone()[0] == 0
    assert flag_cases(con, []) == 0 and con.execute("select count(*) from cases_clean where bulk_closure").fetchone()[0] == 0


def test_req_bulk_1_open_cases_other_scopes_and_empty_departments_are_handled():
    con = table(steady_plus_spike(60, dept=""))
    con.execute("update cases_clean set scope_tier = 'excluded' where id = 'b0'")
    con.execute("update cases_clean set status = 'Open', close_time_utc = NULL where id = 'b1'")
    [g] = bulk_closures(con)
    assert g.department == "(unknown)" and g.n_cases == 58


def test_req_bulk_1_parameters_come_from_params_and_a_lower_bar_flags_more():
    con = table(steady_plus_spike(30))
    assert not bulk_closures(con)
    assert len(bulk_closures(con, replace(DEFAULT, BULK_MIN_CASES=30))) == 1


rows_strategy = st.lists(
    st.tuples(st.sampled_from(["A", "B"]), st.integers(0, 12), st.sampled_from([TEXT, OTHER]), st.integers(1, 90)),
    max_size=40,
)


def expand(spec):
    out = []
    for i, (dept, d, text, n) in enumerate(spec):
        out += [(f"{i}-{k}", dept, day(d), text) for k in range(n)]
    return out


@settings(deadline=None, max_examples=15)
@given(rows_strategy, st.integers(0, 1000))
def test_req_bulk_1_flagged_groups_meet_both_thresholds_and_do_not_depend_on_row_order(spec, seed):
    rows = expand(spec)
    groups = bulk_closures(table(rows))
    for g in groups:
        assert g.n_cases >= DEFAULT.BULK_MIN_CASES and g.ratio >= DEFAULT.BULK_RATIO and g.usual_daily > 0
        assert abs(g.ratio - g.n_cases / g.usual_daily) < 1e-9
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    assert bulk_closures(table(shuffled)) == groups
    keys = [(g.close_date, g.department, g.template) for g in groups]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)


@settings(deadline=None, max_examples=10)
@given(rows_strategy)
def test_req_bulk_2_flagging_changes_only_the_flag_column(spec):
    con = table(expand(spec))
    before = con.execute("select id, system, department, status, close_time_utc, closure_text, scope_tier, coroner_label "
                         "from cases_clean order by id").fetchall()  # fmt: skip
    groups = bulk_closures(con)
    flagged = flag_cases(con, groups)
    after = con.execute("select id, system, department, status, close_time_utc, closure_text, scope_tier, coroner_label "
                        "from cases_clean order by id").fetchall()  # fmt: skip
    assert before == after and flagged == sum(g.n_cases for g in groups)


def test_req_bulk_2_the_pipeline_exports_groups_and_the_flag_reaches_cards(tmp_path):
    from undead311.pipeline import run_pipeline

    out = tmp_path / "out"
    rep = run_pipeline(sample=True, out_dir=out, work_dir=tmp_path / "d", run_time="2026-11-13T00:00:00Z", grid=False)
    doc = json.loads((out / "bulk_closures.json").read_text())
    validate("bulk_closures", doc)
    assert rep.row_counts["bulk_closure_groups"] == len(doc["bulk_closures"])
    cards = [c for f in (out / "cards").glob("*.json") for c in json.loads(f.read_text())["cards"]]
    assert cards and all(isinstance(c["bulk_closure"], bool) for c in cards)
