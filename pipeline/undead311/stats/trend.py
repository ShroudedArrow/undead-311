"""Rolling 6-month trends of the two-number scorecard (REQ-STAT-TREND.1).

Every point is a window of `TREND_MONTHS` calendar months (UTC), never a single month, so one odd month cannot make a
headline. A case belongs to the month its original (incident) closed in. For each family and citywide, and for both tier
sets, the window ending in month `m` pools the eligible originals that closed in months `m - 5 .. m` and gives the
on-time rate and the raw stayed-fixed rate with Wilson intervals, built the same way as the scorecard (REQ-STAT-SF.1-2,
REQ-STAT-TIER.1-2): the same eligible originals, the same denominator (cases with a known `on_time`), the same zombie set.

Only full windows are exported: the first window ends in the month that is `TREND_MONTHS - 1` months after the first
month with an eligible original, and the last ends in the last month with one. Consecutive windows share 5 of their 6 months,
so their intervals are not independent; the payload says so. A window with no cases has null rates with the reason
`no_cases` (REQ-STAT-INT.2).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime

from undead311.detect.model import Case, DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.stats.cohort import eligible_originals
from undead311.stats.intervals import make_rate
from undead311.stats.meta import params_json
from undead311.stats.rates import CITYWIDE, zombie_incident_ids

TREND_MONTHS = 6  # the window length in calendar months (REQ-STAT-TREND.1: never single months)
NOTE = (
    "Each point pools 6 calendar months by the month the original was closed; consecutive points share 5 months, so their "
    "intervals are not independent and a change between neighbouring points is not a test of change."
)


def month_index(when: datetime) -> int:
    """Calendar months since year 0 for a UTC timestamp: consecutive months differ by 1."""
    return when.year * 12 + (when.month - 1)


def month_label(index: int) -> str:
    """`YYYY-MM` of a month index."""
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def trend_rows(
    result: DetectionResult, cases: Mapping[str, Case], data_end: datetime, params: Params = DEFAULT, months: int = TREND_MONTHS
) -> list[dict]:
    """The rolling-window rows, sorted by (family, tier set, window end) (REQ-STAT-TREND.1).

    Counts per (tier set, family, close month) are [closed, known, on time, stayed fixed], the same four counts as
    `rates.scorecards`; a window is the sum over `months` consecutive months."""
    if months < 2:
        raise ValueError("a trend window spans at least 2 months (REQ-STAT-TREND.1)")
    out: list[dict] = []
    for tier_set in ("headline", "all"):
        zombies = zombie_incident_ids(result, tier_set)  # type: ignore[arg-type]
        counts: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
        for inc in eligible_originals(result.incidents, data_end, params, all_tiers=tier_set == "all"):
            m = month_index(inc.close_utc)
            resurrected = inc.incident_id in zombies
            for cid in inc.member_ids:
                c = cases[cid]
                for key in (inc.type_family, CITYWIDE):
                    row = counts[key][m]
                    row[0] += 1
                    if c.on_time is None:
                        continue
                    row[1] += 1
                    if c.on_time:
                        row[2] += 1
                        row[3] += 0 if resurrected else 1
        if not counts:
            continue
        first = min(m for by_month in counts.values() for m in by_month)
        last = max(m for by_month in counts.values() for m in by_month)
        for family in sorted(counts):
            for end in range(first + months - 1, last + 1):
                window = [counts[family][m] for m in range(end - months + 1, end + 1) if m in counts[family]]
                closed, known, on_time, stayed = (sum(w[i] for w in window) for i in range(4))
                out.append({
                    "family": family, "tier_set": tier_set, "window_start": month_label(end - months + 1),
                    "window_end": month_label(end), "n_closed": closed, "n_on_time_known": known,
                    "on_time": make_rate(on_time, known).to_json(), "stayed_fixed_raw": make_rate(stayed, known).to_json(),
                })  # fmt: skip
    return sorted(out, key=lambda r: (r["family"], r["tier_set"], r["window_end"]))


def trend_payload(
    result: DetectionResult,
    cases: Mapping[str, Case],
    data_end: datetime,
    data_version: str,
    params: Params = DEFAULT,
    dataset: str = "full",
) -> dict:
    """The `trends.json` payload (schema `trends`, REQ-STAT-TREND.1, REQ-STAT-EXP.1)."""
    return {
        "data_version": data_version, "dataset": dataset, "params": params_json(params), "seed": None,
        "window_months": TREND_MONTHS, "note": NOTE,
        "rows": trend_rows(result, cases, data_end, params),
    }  # fmt: skip
