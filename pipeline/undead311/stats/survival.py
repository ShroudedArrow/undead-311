"""Survival curves: how long fixes last (REQ-STAT-KM).

Events come from the engine's own `detect()` with WINDOW_DAYS set to SURVIVAL_HORIZON_DAYS (365), so ZD steps 2-9 are not
copied here. For each incident that may be an original (no transferred member), the time is the gap from its closure to its
first resurrection (event) or, with none, the time from closure to the data end capped at the horizon (right-censored).
Times are whole days: an event is rounded up and a censoring time down, so "holding at 7 days" never counts a gap that is
longer than 7 days. Curves are Kaplan-Meier (lifelines) with the exponential Greenwood interval. A resurrection of another
tier is not an event for the headline curve (it matches the stayed-fixed rate, which also counts only headline zombies).

SURVIVAL_HORIZON_DAYS = 365 is a statistics parameter proposed in the durability-stats requirements (methods.md asks for
the 90-day share, which a 60-day window cannot give). The owner records it in methods.md; it is not in
zombie-definition.md.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np
from lifelines import KaplanMeierFitter

from undead311.detect.model import Case, DetectionResult
from undead311.detect.params import DEFAULT, Params

SURVIVAL_HORIZON_DAYS = 365
MIN_GROUP_N = 10  # a department or family curve needs at least this many originals; the citywide curve always exists
MARKS = (7, 30, 90)


def horizon_params(params: Params = DEFAULT) -> Params:
    """The detector parameters of the survival run: the window is the horizon, nothing else changes."""
    return replace(params, WINDOW_DAYS=SURVIVAL_HORIZON_DAYS)


@dataclass(frozen=True)
class Curve:
    name: str
    tier_set: str
    n: int
    events: int
    times: tuple[float, ...]
    survival: tuple[float, ...]
    lo: tuple[float, ...]
    hi: tuple[float, ...]
    at: dict[int, tuple[float | None, float | None, float | None]]  # day -> (share, lo, hi); None past the last time
    half_life: float | None

    def to_json(self) -> dict:
        out: dict = {
            "name": self.name, "tier_set": self.tier_set, "n": self.n, "events": self.events,
            "times": list(self.times), "survival": list(self.survival), "lo": list(self.lo), "hi": list(self.hi),
            "half_life": self.half_life,
        }  # fmt: skip
        for day in MARKS:
            share, lo, hi = self.at[day]
            out[f"at_{day}"], out[f"at_{day}_lo"], out[f"at_{day}_hi"] = share, lo, hi
        return out


def km(durations: list[float], events: list[int], name: str = "all", tier_set: str = "headline") -> Curve | None:
    """Kaplan-Meier curve with Greenwood intervals (REQ-STAT-KM.1-2); None for an empty sample."""
    if not durations:
        return None
    # an event at time 0 would start the curve below 1; it happens just after 0 instead (the curve starts at 1, P2)
    dur = np.asarray([max(d, 1e-9) if e else d for d, e in zip(durations, events, strict=True)], float)
    fit = KaplanMeierFitter().fit(dur, np.asarray(events, int))
    surv = fit.survival_function_.iloc[:, 0]
    ci = fit.confidence_interval_
    times = [float(t) for t in surv.index]
    s = [float(min(1.0, max(0.0, v))) for v in surv.to_numpy()]
    lo = [float(min(1.0, max(0.0, v))) for v in ci.iloc[:, 0].to_numpy()]
    hi = [float(min(1.0, max(0.0, v))) for v in ci.iloc[:, 1].to_numpy()]
    lo = [min(a, b) for a, b in zip(lo, s, strict=True)]  # the interval contains the estimate
    hi = [max(a, b) for a, b in zip(hi, s, strict=True)]
    last = max(durations)
    at: dict[int, tuple[float | None, float | None, float | None]] = {}
    for day in MARKS:
        if day > last:
            at[day] = (None, None, None)
            continue
        i = max(j for j, t in enumerate(times) if t <= day)
        at[day] = (s[i], lo[i], hi[i])
    half = next((t for t, v in zip(times, s, strict=True) if v <= 0.5), None)
    return Curve(name, tier_set, len(durations), int(sum(events)), tuple(times), tuple(s), tuple(lo), tuple(hi), at, half)


def survival_samples(
    result: DetectionResult, data_end: datetime, tier_set: str
) -> list[tuple[str, str | None, float, int]]:
    """(family, department, whole days, event) per incident that may be an original (REQ-STAT-KM.1, .3)."""
    first = {}
    for z in sorted(result.zombies, key=lambda z: (z.gap_days, z.zombie_id)):
        if tier_set == "all" or z.tier == "headline":
            first.setdefault(z.incident_id, z)
    out = []
    for inc in sorted(result.incidents, key=lambda i: i.incident_id):
        if inc.has_transferred_member or (tier_set == "headline" and inc.tier != "core"):
            continue
        z = first.get(inc.incident_id)
        if z is not None:
            out.append((inc.type_family, inc.department, float(math.ceil(z.gap_days)), 1))
        else:
            seen = (data_end - inc.close_utc).total_seconds() / 86_400.0
            out.append((inc.type_family, inc.department, float(max(0, math.floor(min(SURVIVAL_HORIZON_DAYS, seen)))), 0))
    return out


def curves(result: DetectionResult, data_end: datetime) -> list[Curve]:
    """All survival curves: citywide, by family and by department, for the headline tier and all tiers."""
    out: list[Curve] = []
    for tier_set in ("headline", "all"):
        rows = survival_samples(result, data_end, tier_set)
        buckets: dict[str, list[tuple[float, int]]] = {"all": [(d, e) for _f, _d, d, e in rows]}
        by: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for fam, dept, d, e in rows:
            by[f"family:{fam}"].append((d, e))
            by[f"department:{dept or '(unknown)'}"].append((d, e))
        buckets.update({k: v for k, v in by.items() if len(v) >= MIN_GROUP_N})
        for name in sorted(buckets):
            c = km([d for d, _ in buckets[name]], [e for _, e in buckets[name]], name, tier_set)
            if c is not None:
                out.append(c)
    return out


def survival_payload(
    result: DetectionResult, cases: dict[str, Case], data_end: datetime, data_version: str, params: Params, dataset: str
) -> dict:
    """The `survival.json` payload (REQ-STAT-KM, REQ-STAT-EXP.1). `result` is the horizon run."""
    from undead311.stats.meta import params_json

    return {
        "data_version": data_version, "dataset": dataset,
        "params": {**params_json(params), "SURVIVAL_HORIZON_DAYS": SURVIVAL_HORIZON_DAYS}, "seed": None,
        "curves": [c.to_json() for c in curves(result, data_end)],
    }  # fmt: skip
