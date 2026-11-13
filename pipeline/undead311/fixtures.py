"""Test-town loader and golden worksheet format (REQ-DET-GOLD).

`load_test_town` reads the RAW fixture rows of `test_town.csv` into the `cases_norm` table and the normal path then
runs: crosswalk -> catch-all inheritance -> cleaning -> detection. Only SAM snapping (pre-snapped `segment_id`,
`segment_snap_m`) and the Coroner label join (`coroner_label` column) are skipped; the `scenario` and `note` columns
are ignored (REQ-DET-GOLD.1, .4). `golden_result` renders the detector's output in the worksheet format of
docs/TEST_TOWN_WORKSHEET.md so it can be compared with the owner's `expected_zombies.json`.
This module never reads or writes `expected_zombies.json`.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from undead311.detect.cases import cases_from_table
from undead311.detect.core import detect
from undead311.detect.model import DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.ingest.clean import clean, ids_by_reason
from undead311.ingest.crosswalk import apply_crosswalk
from undead311.ingest.normalize import NORM_COLUMNS

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_town.csv"
IGNORED_COLUMNS = ("scenario", "note")


def load_test_town(con: duckdb.DuckDBPyConnection, path: Path = FIXTURE) -> None:
    """Create `cases_norm` (normalized schema) from the raw fixture rows (REQ-DET-GOLD.1, .4)."""
    con.execute("drop table if exists fixture_raw")
    con.execute("create table fixture_raw as select * from read_csv(?, all_varchar=true, header=true)", [str(path)])
    n = lambda col: f"nullif(trim({col}), '')"
    con.execute("drop table if exists cases_norm")
    con.execute(f"""
        create table cases_norm as
        select {n('id')} as id, system,
               try_cast(replace(replace({n('open_time_utc')}, 'T', ' '), 'Z', '') as timestamp) as open_time_utc,
               try_cast(replace(replace({n('close_time_utc')}, 'T', ' '), 'Z', '') as timestamp) as close_time_utc,
               try_cast(replace({n('open_time_local')}, 'T', ' ') as timestamp) as open_time_local,
               try_cast(replace({n('close_time_local')}, 'T', ' ') as timestamp) as close_time_local,
               NULL::timestamp as target_time_utc,
               lower(local_ambiguous) = 'true' as local_ambiguous, false as local_nonexistent, NULL::boolean as on_time,
               {n('status')} as status, {n('closure_text')} as closure_text, {n('closure_code')} as closure_code,
               {n('type_raw')} as type_raw, NULL::varchar as queue, {n('department')} as department,
               {n('neighborhood')} as neighborhood, NULL::varchar as district, {n('street')} as street,
               try_cast(lat as double) as lat, try_cast(lon as double) as lon, {n('source')} as source,
               {n('segment_id')} as segment_id, try_cast(segment_snap_m as double) as segment_snap_m,
               {n('coroner_label')} as coroner_label
        from fixture_raw order by id
    """)  # fmt: skip
    cols = tuple(r[0] for r in con.execute("describe cases_norm").fetchall())
    assert cols == NORM_COLUMNS, cols
    con.execute("drop table fixture_raw")


def run_test_town(
    path: Path = FIXTURE, p: Params = DEFAULT, con: duckdb.DuckDBPyConnection | None = None
) -> tuple[DetectionResult, dict[str, list[str]]]:
    """Load, crosswalk, clean and detect. Returns (result, excluded ids by reason)."""
    con = con or duckdb.connect()
    load_test_town(con, path)
    apply_crosswalk(con)
    clean(con)
    result = detect(cases_from_table(con, "cases_clean"), p)
    return result, ids_by_reason(con)


def golden_result(result: DetectionResult, excluded: dict[str, list[str]]) -> dict:
    """The detector's output in the worksheet format; lists sorted, ID lists inside records sorted (REQ-DET-GOLD.5)."""
    several = [i for i in result.incidents if len(i.member_ids) > 1]
    return {
        "zombies": [
            {
                "incident_id": z.incident_id,
                "member_ids": sorted(z.member_ids),
                "resurrection_id": z.resurrection_id,
                "reports_after": z.reports_after,
                "match_mode": z.match_mode,
                "tier": z.tier,
                "after_temporary_fix": z.after_temporary_fix,
                "chain_id": z.chain_id,
                "times_risen": z.times_risen,
            }
            for z in sorted(result.zombies, key=lambda z: z.incident_id)
        ],
        "planned_followups": [
            {"incident_id": f.incident_id, "resurrection_id": f.resurrection_id}
            for f in sorted(result.planned_followups, key=lambda f: f.incident_id)
        ],
        "separate_deaths": [
            {"incident_id": s.incident_id, "label": s.label, "rereport_id": s.rereport_id}
            for s in sorted(result.separate_deaths, key=lambda s: s.incident_id)
        ],
        "repeat_offenders": [
            {"chain_id": c.chain_id, "times_risen": c.times_risen}
            for c in sorted(result.repeat_offenders, key=lambda c: c.chain_id)
        ],
        "excluded_ids": {
            "placeholder_or_invalid_coords": sorted(
                excluded.get("null_coords", []) + excluded.get("out_of_bounds", []) + excluded.get("placeholder", [])
            ),
            "out_of_scope_type": sorted(excluded.get("unlisted_type", []) + excluded.get("excluded_type", [])),
        },
        "incidents_with_several_members": [
            {"incident_id": i.incident_id, "member_ids": sorted(i.member_ids)}
            for i in sorted(several, key=lambda i: i.incident_id)
        ],
    }


COMPARED_KEYS = (
    "zombies", "planned_followups", "separate_deaths", "repeat_offenders", "excluded_ids",
    "incidents_with_several_members",
)  # fmt: skip
METADATA_KEYS = ("fixture", "written_by")
