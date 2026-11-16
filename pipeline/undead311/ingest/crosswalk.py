"""Type crosswalk, link table and catch-all inheritance (REQ-ING-XWALK, REQ-ING-CATCH).

`apply_crosswalk` turns `cases_norm` into `cases_x` by joining `type_families.csv` on (system, type_raw). A
`type_raw` that is not listed gets NULL family and tier (counted later as `unlisted_type`, REQ-ING-XWALK.2).

Links: a legacy closure text that matches TRANSFER_CLOSURE_RE and names a `BCS-N` case links that legacy case to
the new-system case (`extract_linked_case_id`). The linked legacy IDs become the successor's `predecessor_ids`
(semicolon-joined, sorted). A new-system case with `catch_all = true` (Street Light Other) takes its family and
tier from `resolve_catch_all`: all predecessors listed and agreeing -> inherit (including `excluded`); no link,
an unlisted predecessor type, or disagreement -> the default family with tier `sensitivity` (REQ-ING-CATCH.1-5).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from undead311.ingest.closure_flags import TRANSFER_CLOSURE_RE, extract_linked_case_id, resolve_catch_all

FAMILIES_CSV = Path(__file__).with_name("type_families.csv")


@dataclass
class CrosswalkReport:
    linked_successors: int = 0
    catch_all_outcomes: dict[str, int] = field(default_factory=dict)


def read_families(path: Path = FAMILIES_CSV) -> list[dict[str, str]]:
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def legacy_family_map(rows: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
    """Legacy type_raw -> (type_family, scope_tier), the `families` argument of `resolve_catch_all`."""
    return {r["type_raw"]: (r["type_family"], r["scope_tier"]) for r in rows if r["system"] == "legacy"}


def link_table(con: duckdb.DuckDBPyConnection) -> dict[str, list[tuple[str, str]]]:
    """Successor case ID (upper case) -> [(legacy id, legacy type_raw)] from legacy transfer closure texts (REQ-ING-CATCH.1)."""
    pattern = TRANSFER_CLOSURE_RE.pattern
    rows = con.execute(
        "select id, type_raw, closure_text from cases_norm "
        "where system = 'legacy' and closure_text is not null and regexp_matches(closure_text, ?, 'i')",
        [pattern],
    ).fetchall()
    links: dict[str, list[tuple[str, str]]] = {}
    for legacy_id, type_raw, text in rows:
        linked = extract_linked_case_id(text)
        if linked:
            links.setdefault(linked.upper(), []).append((legacy_id, type_raw or ""))
    for v in links.values():
        v.sort()
    return links


def apply_crosswalk(
    con: duckdb.DuckDBPyConnection, families_csv: Path = FAMILIES_CSV
) -> CrosswalkReport:
    """Create `cases_x` (cases_norm + type_family, scope_tier, city_originated_type, catch_all, predecessor_ids)."""
    rows = read_families(families_csv)
    con.execute("drop table if exists type_families")
    con.execute(
        "create table type_families(system varchar, type_raw varchar, type_family varchar, scope_tier varchar, "
        "city_originated_type boolean, catch_all boolean)"
    )
    con.executemany(
        "insert into type_families values (?,?,?,?,?,?)",
        [
            (r["system"], r["type_raw"], r["type_family"], r["scope_tier"],
             r["city_originated_type"].lower() == "true", r["catch_all"].lower() == "true")
            for r in rows
        ],
    )  # fmt: skip
    families = legacy_family_map(rows)
    links = link_table(con)
    con.execute("drop table if exists case_links")
    con.execute("create table case_links(successor_id varchar, legacy_id varchar)")
    flat = [(succ, lid) for succ, preds in links.items() for lid, _ in preds]
    if flat:
        con.executemany("insert into case_links values (?, ?)", flat)

    report = CrosswalkReport()
    con.execute("drop table if exists catch_all_resolved")
    con.execute(
        "create table catch_all_resolved(id varchar, type_family varchar, scope_tier varchar, predecessor_ids varchar)"
    )
    catch_all = con.execute(
        "select n.id, f.type_family from cases_norm n join type_families f using (system, type_raw) "
        "where n.system = 'new' and f.catch_all"
    ).fetchall()
    resolved = []
    for cid, default_family in catch_all:
        preds = links.get(cid.upper(), [])
        family, tier, ids = resolve_catch_all(default_family, preds, families)
        resolved.append((cid, family, tier, ";".join(ids)))
        if not preds:
            outcome = "unlinked"
        elif tier == "sensitivity":
            outcome = "ambiguous_or_unlisted"
        else:
            outcome = f"inherited_{tier}"
        report.catch_all_outcomes[outcome] = report.catch_all_outcomes.get(outcome, 0) + 1
    if resolved:
        con.executemany("insert into catch_all_resolved values (?,?,?,?)", resolved)

    con.execute("drop table if exists cases_x")
    con.execute("""
        create table cases_x as
        select n.*,
               coalesce(r.type_family, f.type_family) as type_family,
               coalesce(r.scope_tier, f.scope_tier) as scope_tier,
               coalesce(f.city_originated_type, false) as city_originated_type,
               coalesce(f.catch_all, false) as catch_all,
               coalesce(r.predecessor_ids, p.predecessor_ids, '') as predecessor_ids
        from cases_norm n
        left join type_families f on f.system = n.system and f.type_raw = n.type_raw
        left join catch_all_resolved r on r.id = n.id and n.system = 'new'
        left join (select successor_id, string_agg(legacy_id, ';' order by legacy_id) as predecessor_ids
                   from case_links group by 1) p on p.successor_id = upper(n.id) and n.system = 'new'
        order by n.id, n.system
    """)
    report.linked_successors = con.execute(
        "select count(*) from cases_x where system = 'new' and predecessor_ids <> ''"
    ).fetchone()[0]
    return report
