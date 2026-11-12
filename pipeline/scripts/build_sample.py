"""Rebuild data/sample/sample_311.csv from $DATA_DIR/processed/undead311.duckdb (REQ-ING-SAMPLE).

Core-scope rows only. Times follow undead311.ingest.times (both systems are Boston wall-clock, REQ-ING-TZ).
Contents: ALL cross-system candidate pairs (legacy original, new re-report opened 0-60 days after the
legacy close, same family, same 0.0003 degree cell), ~3,500 same-system pairs, and a stratified fill.
Catch-all types (type_families.csv catch_all, i.e. Street Light Other) inherit their family and tier from
the legacy case(s) whose closure text links to them ("Resubmitted as BCS-N"); unlinked or ambiguous ones
are sensitivity-only and left out. predecessor_ids lists those legacy ids (semicolon-joined).
closure_code is the new-system closure_reason code (empty for legacy); pair_survives uses it to drop
'Transitioned' originals.
Run: make data-sample
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import download

from undead311.ingest.closure_flags import (
    extract_linked_case_id,
    is_mirror_pair,
    is_transfer_closure,
    pair_survives,
    resolve_catch_all,
)
from undead311.ingest.times import parse_legacy_stamp, parse_new_system_stamp, to_utc_and_local

SAME_SYSTEM_PAIRS = 3500
FILL_LEGACY, FILL_NEW = 75, 450
COLUMNS = [
    "id", "system", "open_time_utc", "close_time_utc", "open_time_local", "close_time_local",
    "local_ambiguous", "status", "closure_text", "closure_code", "type_raw", "type_family", "scope_tier",
    "city_originated_type", "predecessor_ids", "department", "neighborhood", "street", "lat", "lon", "source",
]  # fmt: skip
PLACEHOLDERS = [(42.3603, -71.0583), (42.3595, -71.0588)]


def scrub(col: str) -> str:
    return (
        f"regexp_replace(regexp_replace(coalesce({col},''), "
        "'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', '<EMAIL>','g'), "
        "'\\(?\\d{3}\\)?[-. ]\\d{3}[-. ]\\d{4}','<PHONE>','g')"
    )


def build_link_table(c) -> dict[str, tuple[str, str, list[str]]]:
    """New-system catch-all case id -> (effective type_family, scope_tier, predecessor ids)."""
    legacy_fam = {
        t: (f, tier)
        for t, f, tier in c.execute("select type_raw, type_family, scope_tier from fam where system='legacy'").fetchall()
    }
    preds: dict[str, list[tuple[str, str]]] = {}
    for lid, ltype, text in c.execute(
        "select case_enquiry_id, type, closure_reason from raw_legacy where closure_reason is not null"
    ).fetchall():
        linked = extract_linked_case_id(text)
        if linked:
            preds.setdefault(linked, []).append((lid, ltype))
    catch_all = c.execute("select type_raw, type_family from fam where system='new' and catch_all").fetchall()
    out = {}
    for traw, default_family in catch_all:
        for (cid,) in c.execute("select distinct case_id from raw_new where service_name=?", [traw]).fetchall():
            out[cid] = resolve_catch_all(default_family, preds.get(cid.upper(), []), legacy_fam)
    return out


def stamp(system: str, text: str | None):
    return parse_legacy_stamp(text) if system == "legacy" else parse_new_system_stamp(text)


def fmt(d, pattern):
    return d.strftime(pattern) if d else ""


def main() -> None:
    data_dir = download.resolve_data_dir()
    root = download.repo_root()
    c = duckdb.connect(str(data_dir / "processed" / "undead311.duckdb"), read_only=True)
    c.execute(f"create temp table fam as select * from read_csv('{root}/pipeline/undead311/ingest/type_families.csv')")
    # naive wall-clock strings; the '+00' suffix on new-system stamps is stripped here and by times.py
    c.execute(f"""create temp table n as
      select 'legacy' as system, case_enquiry_id as id, open_dt::timestamp as open_time, closed_dt::timestamp as close_time,
        case_status as status, nullif({scrub('closure_reason')},'') as closure_text, null::varchar as closure_code, type as type_raw, department,
        neighborhood, location_street_name as street, try_cast(latitude as double) lat,
        try_cast(longitude as double) lon, source from raw_legacy
      union all
      select 'new', case_id, try_cast(regexp_replace(open_date,'\\+00$','') as timestamp),
        try_cast(regexp_replace(close_date,'\\+00$','') as timestamp), case_status,
        nullif({scrub('coalesce(closure_comments, closure_reason)')},''), nullif(closure_reason,''), service_name, assigned_department,
        neighborhood, street_name, try_cast(latitude as double), try_cast(longitude as double), report_source
      from raw_new""")
    c.execute("create temp table link(id varchar, type_family varchar, scope_tier varchar, predecessor_ids varchar)")
    c.executemany(
        "insert into link values (?,?,?,?)",
        [(i, f, t, ";".join(p)) for i, (f, t, p) in build_link_table(c).items()],
    )
    ph = " and ".join(f"not (round(lat,4)={a} and round(lon,4)={b})" for a, b in PLACEHOLDERS)
    c.execute(f"""create temp table s as select n.*, coalesce(link.type_family, fam.type_family) type_family,
        coalesce(link.scope_tier, fam.scope_tier) scope_tier, fam.city_originated_type,
        coalesce(link.predecessor_ids, '') predecessor_ids,
        round(lat/0.0003)::bigint*1000000+round(lon/0.0003)::bigint cell
      from n join fam using(system,type_raw) left join link on link.id=n.id and n.system='new'
      where coalesce(link.scope_tier, fam.scope_tier)='core' and lat between 42.2 and 42.45 and lon between -71.2 and -70.9 and {ph}
        and open_time is not null""")
    join = """from s a join s b on a.cell=b.cell and a.type_family=b.type_family and b.id<>a.id
        and a.close_time is not null and b.open_time>a.close_time and b.open_time<=a.close_time+interval 60 day"""
    c.execute(f"create temp table pairs as select a.id aid, b.id bid, row_number() over (order by hash(a.id||b.id)) rn {join} and a.system=b.system")
    c.execute(f"create temp table pairs_x as select a.id aid, b.id bid {join} and a.system<>b.system")
    c.execute(f"""create temp table pick1 as select aid id from pairs where rn<={SAME_SYSTEM_PAIRS}
        union select bid from pairs where rn<={SAME_SYSTEM_PAIRS} union select aid from pairs_x union select bid from pairs_x""")
    c.execute("""create temp table pick2 as select id, system, row_number() over
        (partition by system, year(open_time), type_family order by hash(id)) rn from s where id not in (select id from pick1)""")
    # timestamps are cast to text to keep the exact wall-clock digits
    rows = c.execute(f"""select id, system, strftime(open_time,'%Y-%m-%d %H:%M:%S'), strftime(close_time,'%Y-%m-%d %H:%M:%S'),
        status, closure_text, closure_code, type_raw, type_family, scope_tier, city_originated_type, predecessor_ids, department, neighborhood, street,
        round(lat,6), round(lon,6), source from s where id in (select id from pick1)
        or id in (select id from pick2 where (system='legacy' and rn<={FILL_LEGACY}) or (system='new' and rn<={FILL_NEW}))
        order by system, open_time, id""").fetchall()
    out, by_id = [], {}
    for (rid, system, ot, ct, status, ctext, ccode, traw, fam, tier, city, pred, dept, nb, street, lat, lon, src) in rows:
        o_utc, o_loc, o_flags = to_utc_and_local(stamp(system, ot))
        c_utc = c_loc = c_flags = None
        if ct:
            c_utc, c_loc, c_flags = to_utc_and_local(stamp(system, ct))
        amb = "local_ambiguous" in o_flags or "local_ambiguous" in (c_flags or ())
        out.append([
            rid, system, fmt(o_utc, "%Y-%m-%dT%H:%M:%SZ"), fmt(c_utc, "%Y-%m-%dT%H:%M:%SZ"),
            fmt(o_loc, "%Y-%m-%dT%H:%M:%S"), fmt(c_loc, "%Y-%m-%dT%H:%M:%S"), str(amb).lower(), status,
            ctext or "", ccode or "", traw, fam, tier, str(bool(city)).lower(), pred, dept or "", nb or "", street or "",
            lat, lon, src or "",
        ])  # fmt: skip
        by_id[rid] = {"system": system, "open_utc": o_utc, "id": rid, "predecessor_ids": pred.split(";") if pred else [], "type_family": fam, "closure_text": ctext, "closure_code": ccode}
    out_path = root / "data" / "sample" / "sample_311.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(out)
    pairs = c.execute("select aid, bid from pairs_x").fetchall()
    surv = sum(pair_survives(by_id[a], by_id[b]) for a, b in pairs)
    transferred = sum(is_transfer_closure(by_id[a]["closure_text"]) for a, _ in pairs)
    mirrors = sum(
        is_mirror_pair(by_id[a]["system"], by_id[b]["system"], by_id[a]["open_utc"], by_id[b]["open_utc"], True, True)
        for a, b in pairs
    )
    continuation = sum(a in by_id[b]["predecessor_ids"] for a, b in pairs)
    size = out_path.stat().st_size
    print(f"rows={len(out)} size_bytes={size} ({size / 1e6:.2f} MB)")
    print(f"cross_system_pairs={len(pairs)} survivors={surv} transferred={transferred} mirrors={mirrors} continuation={continuation}")


if __name__ == "__main__":
    main()
