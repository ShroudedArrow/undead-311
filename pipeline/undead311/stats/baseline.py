"""Same-spot baseline, neighborhood Poisson check and excess resurrections (REQ-STAT-BASE, REQ-STAT-NBR).

`BaselineModel` answers one question per incident: how likely is it that a same-family report appears at the same place
within WINDOW_DAYS of a closure by coincidence?

* Same spot (REQ-STAT-BASE.1): the spot (segment, or a 60 m cell) is watched from its first same-family report to the data
  end. The WINDOW_DAYS after every same-family closure at the spot are dead time (whether or not the closed case was itself
  a resurrection, ops#113): neither the days nor the reports in them count. What is left is the spot's live time and live
  reports. The baseline is a hybrid (methods.md, ops#130, ops#131):
  - Sparse spots (fewer than one report per DENSE_WINDOWS windows over the watched span): the other live reports of season s,
    K_s, fall in the d_s days of the incident's window that lie in season s by chance with probability `d_s / T_s`, T_s being
    the live days of that season: `p_spot = 1 - prod_s (1 - d_s / T_s)^K_s` (ops#111). A season with no live time uses the
    spot's all-season rate. This is unbiased for the Poisson chance of a report in a window (a share of windows that a hit
    makes unusable came out 40% too high at sparse spots, ops#107). The incident's own reports are left out, so a busy spot
    does not raise the baseline of its own originals.
  - Dense spots (at least one report per DENSE_WINDOWS windows): `p_spot` is the share of sliding WINDOW_DAYS windows that
    start on a live day of the incident's season and hold at least one report (`dense_share`). Counting directly drops the
    Poisson formula, which ran low for a spot reported on a near-regular schedule (ops#131). It still assumes something: the
    windows start on live days, which follow a quiet stretch of at least WINDOW_DAYS after a closure, so the share is unbiased
    only for Poisson arrivals. At a spot reported every 70 +- 5 days it is about 0.78 against a true chance of 0 (cautious);
    for bursty arrivals it runs low (about 0.43 against 0.5) and a null town lies above 0 (ops#137, ops#138). Every report counts,
    reports in a dead stretch too, so a real resurrection can only raise the share, which is one reason the excess runs below 0
    at dense spots; it does not make the excess non-positive in every town (docs/METHODS.md lists the limits).
  - A dense spot watched for less than MIN_WINDOWS windows is read the same way (`dense_p`) when it also has one report per
    WINDOW_DAYS (SHORT_DENSE_WINDOWS, counting the first report): spots with fewer reports cannot be told from a lucky sparse
    spot, and a near-regular spot with every report in a dead stretch got a pooled p of about 0 (ops#136).
  - Other spots below MIN_WINDOWS use the higher of the neighborhood rate and the pooled family rate (REQ-STAT-BASE.3): the
    neighborhood rate is the chance at a random point, which runs low for a spot that has reports (ops#136).
* Neighborhood Poisson check (REQ-STAT-NBR.1): lambda = same-family reports per m2 per day in the neighborhood and
  season, leaving out reports within RADIUS_M and +-WINDOW_DAYS of the case; expected = lambda * pi * RADIUS_M^2 *
  WINDOW_DAYS, P = 1 - exp(-expected). It is computed for every incident as a second, independent baseline.

Burstiness (REQ-STAT-BASE.2, methods.md, ops#141): every spot gets a flag (index of dispersion of its monthly report counts above
BURST_DISPERSION, or its reports in fewer than BURST_ACTIVE_SHARE of its observed months). Each excess row also reports the excess
without the flagged spots; the excess is never the headline number.

Excess (REQ-STAT-BASE.2): observed possible zombies minus the sum of the baseline over the same eligible originals,
by department, family and neighborhood, each with a seeded bootstrap interval (REQ-STAT-INT.1). Observed and expected
use the same cohort (fully observed originals), so the two are comparable. The interval carries the error of the baseline
itself: spots are resampled as whole clusters (an original's p and outcome both come from its spot's reports), and each
replicate draws every pooled p again from its windows (originals that share a pooled fallback share the draw, ops#103).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from undead311.detect.model import Case, DetectionResult, Incident, Zombie
from undead311.detect.params import DEFAULT, Params
from undead311.stats.cohort import COS_BOSTON, M_PER_DEG, eligible_originals, season_idx, spot_key
from undead311.stats.intervals import bootstrap_sum_cells

DAY = 86_400.0
MIN_WINDOWS = 4  # REQ-STAT-BASE.3
DENSE_WINDOWS = 2  # a spot with at least one report per DENSE_WINDOWS windows is dense (methods.md hybrid, ops#130, ops#131)
SHORT_DENSE_WINDOWS = 1  # a spot watched for less than MIN_WINDOWS windows is read by its own windows only with one report per window, counting the first (ops#136)
BURST_DISPERSION = 2.0  # a spot is bursty when the index of dispersion of its monthly report counts exceeds this (methods.md, ops#141)
BURST_ACTIVE_SHARE = 0.25  # ... or when its reports fall in fewer than this share of its observed months (methods.md, ops#141)
POOLED_MIN = 100  # pooled windows needed before the citywide fallback is taken for one season, else all seasons
_SEASON_OF_MONTH = np.array([0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 0])  # Jan..Dec -> winter, spring, summer, autumn
UNKNOWN = "(unknown)"
TierSet = str


def season_array(ts: np.ndarray) -> np.ndarray:
    """Season index (0 winter .. 3 autumn) of epoch-second timestamps."""
    months = np.asarray(ts, dtype="int64").astype("datetime64[s]").astype("datetime64[M]").astype("int64") % 12
    return _SEASON_OF_MONTH[months]


def thinned_p(k: int, live_days: float, window_days: float, span_days: float | None = None) -> tuple[float, int] | None:
    """(p, windows) that at least one of `k` other live reports falls in a window of `window_days` (REQ-STAT-BASE.1).

    Each other live report lands in a given window with probability `c = window_days / live_days`, so the chance that none
    does is `(1 - c)^k`; unbiased for the Poisson chance of a report in a window. `windows` counts the windows of the whole
    watched span (`span_days`, default the live days), so whether a spot is trusted never depends on what was reported
    there. None when that span holds less than one window.
    """
    windows = int((live_days if span_days is None else span_days) // window_days)
    if windows < 1:
        return None
    if live_days <= window_days:  # (almost) no live time: every other live report is in the window
        return (1.0 if k > 0 else 0.0), windows
    return 1.0 - (1.0 - window_days / live_days) ** max(k, 0), windows


def season_integrated_p(k: np.ndarray, days: np.ndarray, d: np.ndarray) -> np.ndarray:
    """p = 1 - prod_s (1 - d_s / T_s)^K_s for each row (REQ-STAT-BASE.1, methods.md Primary baseline, ops#111).

    `k` (n, 4) is the other live reports per season of each row's spot, `days` (4,) the spot's live days per season (T_s)
    and `d` (n, 4) the days of each row's window that fall in each season (they sum to WINDOW_DAYS). A season with no live
    time takes the spot's all-season counts and days for its share of the window (a threshold on live days instead was
    tried and biased the baseline down 0.023 on sparse null towns: a season with many reports has fewer live days). A season whose live days do not exceed
    its share of the window has every other live report inside the window: the factor is 0 with a report, 1 without.
    With the whole window in one season this is `thinned_p`. Shared by the excess and the placebo, so both use one estimator.
    """
    k = np.atleast_2d(np.asarray(k, dtype=float))
    d = np.atleast_2d(np.asarray(d, dtype=float))
    t = np.asarray(days, dtype=float)
    none = t <= 0  # seasons without live time
    k_eff = np.where(none[None, :], k.sum(axis=1, keepdims=True), k)
    t_eff = np.where(none, t.sum(), t)[None, :]
    active = d > 1e-9
    enough = t_eff > d
    ratio = np.zeros_like(d)
    np.divide(d, t_eff, out=ratio, where=enough & active)  # share of the season's live days that the window covers
    log_none = np.where(active & enough, k_eff * np.log1p(-ratio), 0.0)
    log_none = log_none.sum(axis=1)
    certain = (active & ~enough & (k_eff > 0)).any(axis=1)  # every other live report is in the window
    return np.where(certain, 1.0, 1.0 - np.exp(log_none))


@dataclass(frozen=True)
class Burst:
    """The burstiness of one spot's reports (REQ-STAT-BASE.2, methods.md "Acceptance and limits", ops#141)."""

    months: int  # calendar months (UTC) from the first report's month to the data end's month, inclusive
    active: int  # months that hold at least one report
    dispersion: float | None  # variance / mean of the monthly counts (None with one month or no reports)
    by_dispersion: bool
    by_concentration: bool

    @property
    def flagged(self) -> bool:
        return self.by_dispersion or self.by_concentration


def burstiness(opens: np.ndarray, t_end: float) -> Burst:
    """Flag a spot whose reports come in bursts or only for a limited period (REQ-STAT-BASE.2, ops#141).

    `opens` are the open times (epoch seconds) of every non-mirror same-family report at the spot; the observed months run from
    the month of the first one to the month of the data end. The spot is bursty when the index of dispersion of its monthly
    counts (sample variance over mean) is above BURST_DISPERSION, or when its reports fall in fewer than BURST_ACTIVE_SHARE of
    the observed months. Both tests read only the reports and the span, never closures or outcomes, so a placebo shift cannot
    change the flag. Bursts and time-limited reporting are where a baseline built from the spot's own history is biased
    (docs/METHODS.md Limits)."""
    if not opens.size:
        return Burst(0, 0, None, False, False)
    month = np.asarray(opens, dtype="int64").astype("datetime64[s]").astype("datetime64[M]").astype("int64")
    last = np.datetime64(int(t_end), "s").astype("datetime64[M]").astype("int64")
    first = int(month.min())
    n_months = max(int(last) - first + 1, int(month.max()) - first + 1)
    counts = np.bincount(month - first, minlength=n_months)
    active = int((counts > 0).sum())
    dispersion = float(counts.var(ddof=1) / counts.mean()) if n_months > 1 else None
    return Burst(n_months, active, dispersion, dispersion is not None and dispersion > BURST_DISPERSION,
                 active < BURST_ACTIVE_SHARE * n_months)  # fmt: skip


@dataclass(frozen=True)
class LiveSpot:
    """A spot's live time: first report, live reports and live days per season, and the merged dead stretches."""

    t0: float
    counts: np.ndarray
    days: np.ndarray
    dead_s: np.ndarray
    dead_e: np.ndarray
    span: np.ndarray = None  # type: ignore[assignment]  # days of each season in the whole watched span
    live_opens: np.ndarray = None  # type: ignore[assignment]  # the live reports after the first, sorted
    all_counts: np.ndarray = None  # type: ignore[assignment]  # every report after the first, per season

    def is_live(self, ts: np.ndarray) -> np.ndarray:
        """True for each time that is outside every dead stretch (start, end]."""
        ts = np.asarray(ts, dtype=float)
        if not self.dead_s.size:
            return np.ones(ts.shape, dtype=bool)
        j = np.searchsorted(self.dead_s, ts, side="left") - 1
        return ~((j >= 0) & (ts <= self.dead_e[np.maximum(j, 0)]))


def ancestor_counts(live: LiveSpot, first_open: float) -> np.ndarray:
    """One live report, in its season: the latest live report before `first_open` (none when it is the spot's first)."""
    j = int(np.searchsorted(live.live_opens, first_open, side="left")) - 1
    out = np.zeros(4, dtype=int)
    if j >= 0:
        out[season_array(live.live_opens[j : j + 1])[0]] = 1
    return out


@dataclass(frozen=True)
class Estimate:
    """The baseline for one incident. `p` is the value used (None when no estimate could be made)."""

    p: float | None
    source: str  # "spot" | "neighborhood" | "citywide" | "none"
    windows: int  # windows of the incident's season in the spot's watched span
    p_nbr: float | None
    expected_nbr: float | None
    cell: tuple | None = None  # a pooled estimate: originals sharing a cell share its error
    n_eff: int = 0  # windows behind a pooled estimate (0: not pooled, so no error is drawn for it)
    cluster: tuple | None = None  # a spot estimate: originals of one spot are resampled together


class BaselineModel:
    """Baseline estimates for the incidents of one detection result (REQ-STAT-BASE, REQ-STAT-NBR)."""

    def __init__(
        self,
        cases: Mapping[str, Case],
        result: DetectionResult,
        params: Params = DEFAULT,
        data_end: datetime | None = None,
        areas_m2: Mapping[str, float] | None = None,
    ) -> None:
        self.cases, self.result, self.params = cases, result, params
        ends = [c.open_utc for c in cases.values()]
        self.data_end = data_end or (max(ends) if ends else None)
        self.t_end = self.data_end.timestamp() if self.data_end else 0.0
        self.t_start = min((c.open_utc.timestamp() for c in cases.values()), default=0.0)
        self.window_s = params.WINDOW_DAYS * DAY
        self.areas_m2 = dict(areas_m2 or {})
        self.mirror = result.mirror_ids
        self._incident_key: dict[str, tuple[str, str]] = {}
        self._incident_of_case: dict[str, Case] = {}
        for inc in sorted(result.incidents, key=lambda i: i.incident_id):
            first = cases[min(inc.member_ids)]
            self._incident_of_case[inc.incident_id] = first
            self._incident_key[inc.incident_id] = (inc.type_family, spot_key(first.segment_id, first.lat, first.lon, params))
        self.groups = self._groups()
        self._build_season_days()
        self._spot_info = self._spots()
        self._own: dict[str, np.ndarray] = {}
        self._dense_cache: dict[tuple[str, str], np.ndarray] = {}
        self._pooled = self._pool()
        self._burst: dict[tuple[str, str], Burst] = {}
        self._estimates: dict[str, Estimate] = {}
        self._nbr_data: dict[tuple[str, str], dict] | None = None
        self.fallbacks: dict[str, int] = {"spot": 0, "neighborhood": 0, "citywide": 0, "none": 0}

    # --- same spot -------------------------------------------------------------------------------------------------
    def _groups(self) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
        """(family, spot) -> (sorted open times, sorted close times) of every non-mirror case, for the spots that have an incident.

        The WINDOW_DAYS after every same-family closure at the spot are dead time, whether or not the closed case was itself
        a resurrection (REQ-STAT-BASE.1, ops#113): the next link of a chain is not a chance report either."""
        needed = set(self._incident_key.values())
        rows: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
        for cid in sorted(self.cases):
            c = self.cases[cid]
            if cid in self.mirror:
                continue
            key = (c.type_family, spot_key(c.segment_id, c.lat, c.lon, self.params))
            if key not in needed:
                continue
            rows[key].append((c.open_utc.timestamp(), c.close_utc.timestamp() if c.is_closed else math.inf))  # type: ignore[union-attr]
        out = {}
        for key in sorted(rows):
            pairs = sorted(rows[key])
            out[key] = (
                np.array([p[0] for p in pairs]),
                np.sort(np.array([p[1] for p in pairs if p[1] != math.inf])),
            )
        return out

    def _build_season_days(self) -> None:
        """Cumulative days of each season from the first report, by day, so any stretch of time is two lookups."""
        n = max(int((self.t_end - self.t_start) // DAY) + 2, 1) + math.ceil(self.params.WINDOW_DAYS) + 1  # + one window
        self._day_season = season_array(self.t_start + DAY * np.arange(n))
        self._cum = np.zeros((4, n + 1))
        for s in range(4):
            self._cum[s, 1:] = np.cumsum(self._day_season == s)

    def _season_days_upto(self, ts: np.ndarray) -> np.ndarray:
        """Days of each season from the first report to each time in `ts` (shape (4, len(ts)), fractional days)."""
        x = np.clip((np.asarray(ts, dtype=float) - self.t_start) / DAY, 0.0, self._cum.shape[1] - 2.0)
        i = np.floor(x).astype(int)
        frac = x - i
        out = self._cum[:, i].copy()
        out[self._day_season[i], np.arange(i.size)] += frac  # the part of day i that has passed counts for its season
        return out

    def window_season_days(self, ts: np.ndarray) -> np.ndarray:
        """Days of each season in the window of WINDOW_DAYS that starts at each time in `ts`. Shape (len(ts), 4); each row
        sums to WINDOW_DAYS (REQ-STAT-BASE.1: d_s)."""
        ts = np.asarray(ts, dtype=float)
        return (self._season_days_upto(ts + self.window_s) - self._season_days_upto(ts)).T

    def live_spot(self, opens: np.ndarray, closes: np.ndarray) -> LiveSpot:
        """The watched time of a spot with the `WINDOW_DAYS` that follow each closure taken out (REQ-STAT-BASE.1).

        The spot is watched from its first report to the data end. A stretch that follows a closure is where a
        resurrection would show, so it is neither counted as time nor are its reports counted as chance reports (this is
        what keeps real resurrections out of the baseline). What is left is the live time, and the live reports in it.
        """
        t0, t1 = float(opens[0]), self.t_end
        dead_s = np.empty(0)
        dead_e = np.empty(0)
        if closes.size:
            ends = closes + self.window_s
            new = np.r_[True, closes[1:] > np.maximum.accumulate(ends)[:-1]]
            first = np.flatnonzero(new)
            dead_s, dead_e = closes[first], np.maximum.reduceat(ends, first)
        a = np.clip(np.r_[t0, dead_e], t0, t1)
        b = np.clip(np.r_[dead_s, t1], t0, t1)
        keep = b > a
        a, b = a[keep], b[keep]
        days = (self._season_days_upto(b) - self._season_days_upto(a)).sum(axis=1) if a.size else np.zeros(4)
        live = LiveSpot(t0, np.zeros(4, dtype=int), days, dead_s, dead_e)
        after = opens[opens > t0]
        after = after[live.is_live(after)]
        counts = np.bincount(season_array(after), minlength=4) if after.size else np.zeros(4, dtype=int)
        edge = self._season_days_upto(np.array([t0, t1]))
        every = opens[opens > t0]
        all_counts = np.bincount(season_array(every), minlength=4) if every.size else np.zeros(4, dtype=int)
        return LiveSpot(t0, counts, days, dead_s, dead_e, edge[:, 1] - edge[:, 0], after, all_counts)

    def _spots(self) -> dict[tuple[str, str], LiveSpot]:
        return {key: self.live_spot(opens, closes) for key, (opens, closes) in self.groups.items()}

    def own_after(self, inc: Incident) -> np.ndarray:
        """Live reports of the spot to leave out of the incident's baseline, per season (REQ-STAT-BASE.1).

        These are the incident's own member reports that are live (never chance reports). An incident whose members all
        opened in a dead stretch (a resurrection of an earlier incident) leaves out the live report that started the
        stretch: a spot is only seen to have such an incident because it has that report, so it looks busier than it is
        (a null town with 300 spots gave p 0.38 for these incidents against an observed 0.26 without it).
        """
        got = self._own.get(inc.incident_id)
        if got is not None:
            return got
        key = self._incident_key[inc.incident_id]
        live = self._spot_info[key]
        opens = []
        for mid in inc.member_ids:
            c = self.cases[mid]
            if mid in self.mirror or (c.type_family, spot_key(c.segment_id, c.lat, c.lon, self.params)) != key:
                continue
            opens.append(c.open_utc.timestamp())
        arr = np.array(opens)
        arr = arr[(arr > live.t0) & live.is_live(arr)] if arr.size else arr
        got = np.bincount(season_array(arr), minlength=4) if arr.size else np.zeros(4, dtype=int)
        if not got.any() and opens:  # born in a dead stretch: leave out the live report that started the stretch
            got = ancestor_counts(live, min(opens))
        self._own[inc.incident_id] = got
        return got

    def own_all(self, inc: Incident) -> np.ndarray:
        """The incident's member reports after the spot's first report, per season, live or not."""
        key = self._incident_key[inc.incident_id]
        t0 = self._spot_info[key].t0
        opens = [
            self.cases[mid].open_utc.timestamp()
            for mid in inc.member_ids
            if mid not in self.mirror and self.cases[mid].open_utc.timestamp() > t0
            and (self.cases[mid].type_family, spot_key(self.cases[mid].segment_id, self.cases[mid].lat,
                                                      self.cases[mid].lon, self.params)) == key
        ]  # fmt: skip
        return np.bincount(season_array(np.array(opens)), minlength=4) if opens else np.zeros(4, dtype=int)

    def is_dense(self, key: tuple[str, str]) -> bool:
        """A dense spot has at least one report per DENSE_WINDOWS windows over its watched span (methods.md hybrid baseline,
        REQ-STAT-BASE.1). Reports and span do not depend on closures, so a placebo shift never changes the class."""
        live = self._spot_info.get(key)
        if live is None or live.all_counts is None:
            return False
        span = float(live.span.sum())
        return span > 0 and float(live.all_counts.sum()) * DENSE_WINDOWS * self.params.WINDOW_DAYS >= span

    def burst(self, key: tuple[str, str]) -> Burst:
        """The burstiness flag of a spot (REQ-STAT-BASE.2): from the open times of every non-mirror report there."""
        got = self._burst.get(key)
        if got is None:
            got = self._burst[key] = burstiness(self.groups[key][0] if key in self.groups else np.empty(0), self.t_end)
        return got

    def is_bursty(self, incident: Incident) -> bool:
        """True when the incident's spot is flagged bursty (REQ-STAT-BASE.2)."""
        return self.burst(self._incident_key[incident.incident_id]).flagged

    def burst_summary(self, incidents: list[Incident]) -> dict[str, int]:
        """Spots and originals behind `incidents` by burstiness flag (REQ-STAT-BASE.2, ops#141), for `excess.json`."""
        keys = {self._incident_key[i.incident_id] for i in incidents}
        flags = {k: self.burst(k) for k in keys}
        return {
            "spots": len(keys),
            "flagged_spots": sum(b.flagged for b in flags.values()),
            "flagged_by_dispersion": sum(b.by_dispersion for b in flags.values()),
            "flagged_by_concentration": sum(b.by_concentration for b in flags.values()),
            "originals": len(incidents),
            "flagged_originals": sum(self.is_bursty(i) for i in incidents),
        }

    def dense_share(self, opens: np.ndarray, live: LiveSpot) -> np.ndarray:
        """Share of sliding WINDOW_DAYS windows that contain a report, for the dense estimator (REQ-STAT-BASE.1, ops#131).

        Windows start on each whole day from the spot's first report to WINDOW_DAYS before the data end, only on days outside
        the dead stretches after closures, and a window holds a report when one opens in (start, start + WINDOW_DAYS]. Every
        non-mirror report counts, the ones in a dead stretch too: counting directly needs no Poisson formula (which is
        wrong for a spot reported on a near-regular schedule), and a real resurrection can only raise the share, the
        cautious direction. It still assumes the windows that start on live days are typical of the spot, which holds for
        Poisson arrivals and fails for bursts, fixed schedules and spots whose reports stop (see docs/METHODS.md). Returns 5 values: the share of the windows that start in each season
        (nan when none do), then the share over all seasons (nan when there are no windows)."""
        out = np.full(5, np.nan)
        n = math.floor((self.t_end - self.window_s - live.t0) / DAY) + 1
        if n < 1:
            return out
        starts = live.t0 + DAY * np.arange(n)
        starts = starts[live.is_live(starts)]
        if not starts.size:
            return out
        hit = np.searchsorted(opens, starts + self.window_s, side="right") > np.searchsorted(opens, starts, side="right")
        seasons = season_array(starts)
        for x in range(4):
            if (seasons == x).any():
                out[x] = hit[seasons == x].mean()
        out[4] = hit.mean()
        return out

    def spot_p(self, inc: Incident, s: int | None = None) -> tuple[float, int] | None:
        """(p_spot, windows) of the incident's spot; None when the spot's live time holds less than one window.

        p follows the days of the incident's own window in each season (REQ-STAT-BASE.1, ops#111). `windows` counts the
        windows of season `s` (default: the season of the closure) in the watched span, which REQ-STAT-BASE.3 compares
        with MIN_WINDOWS."""
        live = self._spot_info.get(self._incident_key[inc.incident_id])
        if live is None:  # only mirror copies at the spot: nothing to watch
            return None
        s = season_idx(inc.close_utc) if s is None else s
        windows = int(float(live.span[s]) // self.params.WINDOW_DAYS)
        if windows < 1:
            return None
        key = self._incident_key[inc.incident_id]
        if self.is_dense(key):
            if key not in self._dense_cache:
                self._dense_cache[key] = self.dense_share(self.groups[key][0], live)
            share = self._dense_cache[key]
            got = share[s] if not math.isnan(share[s]) else share[4]
            if not math.isnan(got):
                return float(got), windows
        k = live.counts - self.own_after(inc)
        d = self.window_season_days(np.array([inc.close_utc.timestamp()]))
        return float(season_integrated_p(np.maximum(k, 0)[None, :], live.days, d)[0]), windows

    def dense_p(self, inc: Incident, s: int | None = None) -> float | None:
        """The dense estimator for a dense spot watched for less than MIN_WINDOWS windows of the closure's season (REQ-STAT-BASE.1,
        REQ-STAT-BASE.3, ops#136). None when the spot is not dense or has no window that starts on a live day.

        A near-regular spot has its reports inside the dead stretches after closures, so the pooled Poisson rate of the fallback
        runs near 0 and gives a positive excess however short the spot's history (ops#131, ops#136). The spot's own sliding-window
        share has no such blind spot and needs only one watched window: it is the same quantity the long dense spots use."""
        key = self._incident_key[inc.incident_id]
        live = self._spot_info.get(key)
        if live is None or not self.is_dense(key):
            return None
        if (float(live.all_counts.sum()) + 1.0) * SHORT_DENSE_WINDOWS * self.params.WINDOW_DAYS < float(live.span.sum()):
            return None  # fewer than one report per window: too few reports to tell a dense spot from a lucky sparse one
        s = season_idx(inc.close_utc) if s is None else s
        if key not in self._dense_cache:
            self._dense_cache[key] = self.dense_share(self.groups[key][0], live)
        share = self._dense_cache[key]
        got = share[s] if not math.isnan(share[s]) else share[4]
        return None if math.isnan(got) else float(got)

    def _pool(self) -> dict[tuple[str, int], tuple[int, float]]:
        """Windows and pooled p of every family and season (season -1: all seasons), for the fallback (REQ-STAT-BASE.3).

        The pooled rate of a family and season is the live reports over the live days of every watched spot of the family
        (`sum K_s / sum T_s`): the WINDOW_DAYS after every same-family closure are left out of both, so a real resurrection
        and a link of a chain are not chance reports (REQ-STAT-BASE.1, ops#113). Adding up over all spots keeps the live time
        long enough for a rate, which a spot that falls back (watched for a short time) cannot give alone; a per-spot p
        averaged over such spots came out 30% high on a null town (ops#114). An incident's pooled p is
        `1 - exp(-sum_s rate_s * d_s)` over the days d_s its window has in each season (a season without live time takes the
        all-season rate), and the pooled p of a family and season is the mean of these over its incidents. One rate for the
        family treats its spots alike: on a town whose spots differ 10-fold it runs low for the busy ones, which is why only
        the spots watched for less than MIN_WINDOWS windows use it (ops#114).
        """
        w = self.params.WINDOW_DAYS
        k_sum: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(4))
        t_sum: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(4))
        for key in sorted(self._spot_info):
            k_sum[key[0]] += self._spot_info[key].counts
            t_sum[key[0]] += self._spot_info[key].days
        rate: dict[str, np.ndarray] = {}
        for fam, k_f in k_sum.items():
            t_f = t_sum[fam]
            all_rate = k_f.sum() / t_f.sum() if t_f.sum() > 0 else 0.0
            rate[fam] = np.array([k_f[x] / t_f[x] if t_f[x] > 0 else all_rate for x in range(4)])
        total: dict[tuple[str, int], float] = defaultdict(float)
        count: dict[tuple[str, int], int] = defaultdict(int)
        windows: dict[tuple[str, int], int] = defaultdict(int)
        seen: set[tuple[tuple[str, str], int]] = set()
        for inc in sorted(self.result.incidents, key=lambda i: i.incident_id):
            s = season_idx(inc.close_utc)
            key = self._incident_key[inc.incident_id]
            live = self._spot_info.get(key)
            if live is None:
                continue
            n_win = int(float(live.span[s]) // w)
            if n_win < 1:
                continue
            d = self.window_season_days(np.array([inc.close_utc.timestamp()]))[0]
            p_inc = float(1.0 - math.exp(-float((rate[key[0]] * d).sum())))
            for ps in (s, -1):
                total[(key[0], ps)] += p_inc
                count[(key[0], ps)] += 1
                if (key, ps) not in seen:
                    seen.add((key, ps))
                    windows[(key[0], ps)] += n_win if ps == s else sum(int(live.span[x] // w) for x in range(4))
        return {k: (windows[k], total[k] / count[k]) for k in count}

    # --- neighborhood ------------------------------------------------------------------------------------------------
    def _nbr_arrays(self) -> dict[tuple[str, str], dict]:
        if self._nbr_data is not None:
            return self._nbr_data
        from scipy.spatial import cKDTree

        rows: dict[tuple[str, str], list[tuple[float, float, float]]] = defaultdict(list)
        for cid in sorted(self.cases):
            c = self.cases[cid]
            if cid in self.mirror or not c.neighborhood:
                continue
            rows[(c.neighborhood, c.type_family)].append(
                (c.open_utc.timestamp(), c.lon * M_PER_DEG * COS_BOSTON, c.lat * M_PER_DEG)
            )
        data: dict[tuple[str, str], dict] = {}
        for key, vals in rows.items():
            arr = np.array(sorted(vals))
            seasons = season_array(arr[:, 0])
            data[key] = {
                "t": arr[:, 0], "season": seasons, "tree": cKDTree(arr[:, 1:3]),
                "by_season": np.bincount(seasons, minlength=4),
            }  # fmt: skip
        self._nbr_data = data
        self._season_days = self._days_per_season()
        return data

    def _days_per_season(self) -> np.ndarray:
        """Days of each season inside the observation span (first report to data end)."""
        n_days = int((self.t_end - self.t_start) // DAY) + 1
        days = self.t_start + DAY * np.arange(max(n_days, 0))
        days = days[days <= self.t_end]
        return np.bincount(season_array(days), minlength=4).astype(float) if days.size else np.zeros(4)

    def nbr(self, inc: Incident) -> tuple[float, float] | None:
        """(P, expected) for the neighborhood Poisson check, or None without a neighborhood area (REQ-STAT-NBR.1)."""
        area = self.areas_m2.get(inc.neighborhood or "")
        if not area or not inc.neighborhood:
            return None
        data = self._nbr_arrays().get((inc.neighborhood, inc.type_family))
        s = season_idx(inc.close_utc)
        days = self._season_days[s]
        if days <= 0:
            return None
        if data is None:
            return 0.0, 0.0  # no same-family report in the neighborhood at all
        first = self._incident_of_case[inc.incident_id]
        point = (first.lon * M_PER_DEG * COS_BOSTON, first.lat * M_PER_DEG)
        near = data["tree"].query_ball_point(point, r=self.params.RADIUS_M)
        t_close = inc.close_utc.timestamp()
        idx = np.asarray(near, dtype=int)
        excluded = 0
        if idx.size:
            excluded = int(((np.abs(data["t"][idx] - t_close) <= self.window_s) & (data["season"][idx] == s)).sum())
        lam = max(0, int(data["by_season"][s]) - excluded) / (area * days)
        expected = lam * math.pi * self.params.RADIUS_M**2 * self.params.WINDOW_DAYS
        return 1.0 - math.exp(-expected), expected

    # --- estimates ---------------------------------------------------------------------------------------------------
    def estimate(self, inc: Incident) -> Estimate:
        """The baseline of one incident, with the fallback chain of REQ-STAT-BASE.3 (cached)."""
        got = self._estimates.get(inc.incident_id)
        if got is not None:
            return got
        key = self._incident_key[inc.incident_id]
        s = season_idx(inc.close_utc)
        got = self.spot_p(inc, s)
        windows = got[1] if got else 0
        nbr = self.nbr(inc)
        p_nbr, e_nbr = (nbr if nbr else (None, None))
        if got is not None and windows >= MIN_WINDOWS:
            est = Estimate(got[0], "spot", windows, p_nbr, e_nbr, None, 0, ("spot", *key))
        elif (p_dense := self.dense_p(inc, s)) is not None:  # a dense spot is read by its own windows however short (ops#136)
            est = Estimate(p_dense, "spot", windows, p_nbr, e_nbr, None, 0, ("spot", *key))
        else:
            season_key = s
            n, pool_p = self._pooled.get((inc.type_family, s), (0, 0.0))
            if n < POOLED_MIN:  # too few windows for one season: pool all seasons of the family
                season_key = -1
                n, pool_p = self._pooled.get((inc.type_family, -1), (0, 0.0))
            # The neighborhood rate is the first fallback (REQ-STAT-BASE.3), but it is the chance at a random point and a spot that
            # has reports is busier than a random point, so on its own it runs low and gave an excess above 0 on a null town of
            # sparse spots (ops#136). The fallback is the higher of the two: never lower than the family's own live rate.
            if p_nbr is not None and not (n and pool_p > p_nbr):
                est = Estimate(p_nbr, "neighborhood", windows, p_nbr, e_nbr)
            else:
                est = Estimate(pool_p if n else None, "citywide" if n else "none", windows, p_nbr, e_nbr,
                               ("pool", inc.type_family, season_key), n)  # fmt: skip
        self._estimates[inc.incident_id] = est
        return est

    def p(self, inc: Incident) -> float | None:
        return self.estimate(inc).p

    def fallback_counts(self, incidents: list[Incident]) -> dict[str, int]:
        """How many of `incidents` used each source (REQ-STAT-BASE.3: the fallback is counted)."""
        out = {"spot": 0, "neighborhood": 0, "citywide": 0, "none": 0}
        for inc in incidents:
            out[self.estimate(inc).source] += 1
        return out

    def zombie_baselines(self) -> dict[str, float]:
        """`baseline_p` per zombie for the engine's confidence score (REQ-STAT-BASE.4)."""
        by_inc = {i.incident_id: i for i in self.result.incidents}
        out: dict[str, float] = {}
        for z in self.result.zombies:
            p = self.p(by_inc[z.incident_id])
            if p is not None:
                out[z.zombie_id] = min(1.0, max(0.0, p))
        return out


@dataclass(frozen=True)
class ExcessRow:
    kind: str
    name: str
    tier_set: TierSet
    observed: int
    expected: float
    excess: float
    lo: float
    hi: float
    n_originals: int
    expected_nbr: float | None
    excess_nbr: float | None
    n_fallback: int
    n_bursty: int = 0  # originals at spots flagged bursty (REQ-STAT-BASE.2)
    unflagged: ExcessUnflagged | None = None  # the same row without the flagged spots; None when none is left

    def to_json(self) -> dict:
        return {
            "kind": self.kind, "name": self.name, "tier_set": self.tier_set, "observed": self.observed,
            "expected": self.expected, "excess": self.excess, "lo": self.lo, "hi": self.hi,
            "n_originals": self.n_originals, "expected_nbr": self.expected_nbr, "excess_nbr": self.excess_nbr,
            "n_fallback": self.n_fallback, "n_bursty": self.n_bursty,
            "without_bursty": None if self.unflagged is None else self.unflagged.to_json(),
        }  # fmt: skip


@dataclass(frozen=True)
class ExcessUnflagged:
    """An excess row restricted to the originals at spots that are not flagged bursty (REQ-STAT-BASE.2)."""

    observed: int
    expected: float
    excess: float
    lo: float
    hi: float
    n_originals: int

    def to_json(self) -> dict:
        return {"observed": self.observed, "expected": self.expected, "excess": self.excess, "lo": self.lo,
                "hi": self.hi, "n_originals": self.n_originals}  # fmt: skip


def zombie_by_incident(zombies: list[Zombie], tier_set: TierSet) -> dict[str, Zombie]:
    """Each incident's resurrection in the tier set: headline only, or every tier (REQ-STAT-TIER.2)."""
    return {z.incident_id: z for z in zombies if tier_set == "all" or z.tier == "headline"}


def excess_interval(vals: list[tuple], rng: np.random.Generator, boot: int) -> tuple[float, float]:
    """Seeded bootstrap interval of the excess of `vals` (REQ-STAT-INT.1, REQ-STAT-BASE.2).

    Each row is (outcome, p, expected_nbr, fallback, cell, n_eff, cluster, bursty). Whole spots are resampled and every pooled
    p is drawn again from its windows."""
    cell_ids: dict[tuple, int] = {}
    cells = [-1 if v[4] is None else cell_ids.setdefault(v[4], len(cell_ids)) for v in vals]
    cell_p = [0.0] * len(cell_ids)
    cell_n = [0.0] * len(cell_ids)
    for v, c in zip(vals, cells, strict=True):
        if c >= 0:
            cell_p[c], cell_n[c] = v[1], float(v[5])
    cluster_ids: dict[tuple, int] = {}
    clusters = [-1 if v[6] is None else cluster_ids.setdefault(v[6], len(cluster_ids)) for v in vals]
    ci = bootstrap_sum_cells([v[0] - v[1] for v in vals], cells, cell_p, cell_n, rng, boot, clusters=clusters)
    assert ci is not None
    return ci


def excess_rows(
    model: BaselineModel, seed: int = 311, boot: int = 1000
) -> list[ExcessRow]:
    """Observed, expected and excess by department, family and neighborhood, headline and all tiers (REQ-STAT-BASE.2).

    Originals without an estimate (no spot, neighborhood or pooled windows) are left out of the cohort and counted
    nowhere in `observed` either, so observed and expected always cover the same originals.

    Every row also carries the same excess without the originals at spots flagged bursty (REQ-STAT-BASE.2, ops#141). Its
    interval comes from a second generator seeded (seed, 1), so the intervals of the full rows never depend on the flag.
    """
    rng = np.random.Generator(np.random.PCG64(seed))
    rng_flag = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 1])))
    rows: list[ExcessRow] = []
    for tier_set in ("headline", "all"):
        zs = zombie_by_incident(model.result.zombies, tier_set)
        groups: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        for inc in eligible_originals(model.result.incidents, model.data_end, model.params, all_tiers=tier_set == "all"):
            est = model.estimate(inc)
            if est.p is None:
                continue
            row = (1.0 if inc.incident_id in zs else 0.0, est.p, est.expected_nbr, est.source != "spot", est.cell, est.n_eff,
                   est.cluster, model.is_bursty(inc))
            for kind, name in (("department", inc.department or UNKNOWN), ("family", inc.type_family),
                               ("neighborhood", inc.neighborhood or UNKNOWN)):  # fmt: skip
                groups[(kind, name)].append(row)
        for (kind, name) in sorted(groups):
            vals = groups[(kind, name)]
            obs = sum(v[0] for v in vals)
            exp = sum(v[1] for v in vals)
            nbr = [v[2] for v in vals]
            e_nbr = None if any(x is None for x in nbr) else float(sum(nbr))  # type: ignore[arg-type]
            ci = excess_interval(vals, rng, boot)
            kept = [v for v in vals if not v[7]]
            without = None
            if kept:
                k_obs, k_exp = sum(v[0] for v in kept), sum(v[1] for v in kept)
                k_ci = excess_interval(kept, rng_flag, boot)
                without = ExcessUnflagged(int(k_obs), k_exp, k_obs - k_exp, k_ci[0], k_ci[1], len(kept))
            rows.append(ExcessRow(kind, name, tier_set, int(obs), exp, obs - exp, ci[0], ci[1], len(vals), e_nbr,
                                  None if e_nbr is None else obs - e_nbr, sum(1 for v in vals if v[3]),
                                  len(vals) - len(kept), without))  # fmt: skip
    return rows
