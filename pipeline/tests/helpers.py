"""Shared builders for detector tests (not a test module)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from undead311.detect.model import Case
from undead311.detect.params import DEFAULT, Params

LAT0, LON0 = 42.30, -71.10
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(LAT0))
T0 = datetime(2024, 3, 4, 12, 0, tzinfo=UTC)


def at(x_m: float, y_m: float = 0.0) -> tuple[float, float]:
    """(lat, lon) of a point x_m east and y_m north of the test origin."""
    return LAT0 + y_m / M_LAT, LON0 + x_m / M_LON


def day(n: float, hours: float = 0.0) -> datetime:
    return T0 + timedelta(days=n, hours=hours)


def mk(
    cid: str,
    open_day: float,
    close_day: float | None = None,
    *,
    x: float = 0.0,
    y: float = 0.0,
    system: str = "legacy",
    family: str = "pothole_roadway",
    segment: str | None = None,
    snap: float | None = 4.0,
    label: str | None = "resolved",
    tier: str = "core",
    source: str | None = "Constituent Call",
    code: str | None = None,
    text: str | None = None,
    nodes: tuple[tuple[str, float], ...] = (),
    preds: tuple[str, ...] = (),
    city_type: bool = False,
    catch_all: bool = False,
    open_hours: float = 0.0,
    close_hours: float = 0.0,
) -> Case:
    lat, lon = at(x, y)
    closed = close_day is not None
    return Case(
        id=cid,
        system=system,  # type: ignore[arg-type]
        open_utc=day(open_day, open_hours),
        close_utc=day(close_day, close_hours) if closed else None,
        type_family=family,
        type_raw=family,
        scope_tier=tier,  # type: ignore[arg-type]
        city_originated_type=city_type,
        catch_all=catch_all,
        predecessor_ids=preds,
        source=source,
        closure_text=text,
        closure_code=code,
        coroner_label=label if closed else None,
        status="Closed" if closed else "Open",
        lat=lat,
        lon=lon,
        segment_id=segment,
        segment_snap_m=snap if segment else None,
        near_nodes=nodes,
    )


def params(**kw) -> Params:
    from dataclasses import replace

    return replace(DEFAULT, **kw)


def examples(n: int) -> int:
    """REQ-OPS-PBT.1: a property's own example count, scaled by the active Hypothesis profile.

    `@settings(max_examples=N)` overrides the profile, so a pinned count would stay at 1x in the nightly deep run. Write
    `max_examples=examples(N)` instead: N under `fast`, 10 x N under `deep` (the ratio of the two profiles in conftest.py).
    A test checks that no property pins a bare number."""
    from hypothesis import settings

    return n * max(1, settings.default.max_examples // settings.get_profile("fast").max_examples)


def read_zombies(folder) -> list[dict]:
    """Every zombie of an export folder, from its `zombies/` shards, sorted by zombie_id (REQ-EXP-SIZE.3)."""
    import json
    from pathlib import Path

    rows = [z for f in sorted((Path(folder) / "zombies").glob("*.json")) if f.name != "index.json"
            for z in json.loads(f.read_text())["zombies"]]
    return sorted(rows, key=lambda z: z["zombie_id"])


def payload_zombies(payloads: dict) -> list[dict]:
    """The same from `build_payloads` output (file name -> payload)."""
    rows = [z for k, v in payloads.items() if k.startswith("zombies/") and k != "zombies/index.json" for z in v["zombies"]]
    return sorted(rows, key=lambda z: z["zombie_id"])
