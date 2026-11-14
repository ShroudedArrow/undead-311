"""Same-spot baseline, neighborhood Poisson check and excess resurrections (REQ-STAT-BASE, REQ-STAT-NBR).

`BaselineModel` answers one question per incident: how likely is it that a same-family report appears at the same place
within WINDOW_DAYS of a closure by coincidence?

* Same spot (REQ-STAT-BASE.1): the comparable windows of the incident's spot (segment, or a 60 m cell) and family. A
  window is WINDOW_DAYS long, starts at the spot's first same-family report plus a whole number of windows (k >= 1,
  so the first report is never counted), ends by the data end, and starts at least WINDOW_DAYS after any same-family
  closure at the spot. `p_spot` is the share of windows of the incident's season that contain at least one same-family
  report (mirror copies are one report, not two). Counting every report is the cautious choice: it can only raise
  `p_spot`.
* Fewer than MIN_WINDOWS windows (REQ-STAT-BASE.3): the neighborhood estimate (`P` below) is used, and when there is no
  neighborhood area, the same-family windows of every spot of the same season (at least POOLED_MIN of them, else of any
  season: "citywide"). The
  number of incidents that fell back, and to what, is exported.
* Neighborhood Poisson check (REQ-STAT-NBR.1): lambda = same-family reports per m2 per day in the neighborhood and
  season, leaving out reports within RADIUS_M and +-WINDOW_DAYS of the case; expected = lambda * pi * RADIUS_M^2 *
  WINDOW_DAYS, P = 1 - exp(-expected). It is computed for every incident as a second, independent baseline.

Excess (REQ-STAT-BASE.2): observed possible zombies minus the sum of the baseline over the same eligible originals,
by department, family and neighborhood, each with a seeded bootstrap interval (REQ-STAT-INT.1). Observed and expected
use the same cohort (fully observed originals), so the two are comparable.
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
from undead311.stats.intervals import bootstrap_sum

DAY = 86_400.0
MIN_WINDOWS = 4  # REQ-STAT-BASE.3
POOLED_MIN = 100  # pooled windows needed before the citywide fallback is taken for one season, else all seasons
_SEASON_OF_MONTH = np.array([0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 0])  # Jan..Dec -> winter, spring, summer, autumn
UNKNOWN = "(unknown)"
TierSet = str


def season_array(ts: np.ndarray) -> np.ndarray:
    """Season index (0 winter .. 3 autumn) of epoch-second timestamps."""
    months = np.asarray(ts, dtype="int64").astype("datetime64[s]").astype("datetime64[M]").astype("int64") % 12
    return _SEASON_OF_MONTH[months]


def window_counts(opens: np.ndarray, closes: np.ndarray, t_end: float, window_s: float) -> tuple[np.ndarray, np.ndarray]:
    """(comparable windows, windows with a report) per season for one spot and family (REQ-STAT-BASE.1).

    `opens` and `closes` are sorted epoch seconds of the same-family reports and closures at the spot.
    """
    n = np.zeros(4, dtype=int)
    hit = np.zeros(4, dtype=int)
    if opens.size == 0:
        return n, hit
    t0 = float(opens[0])
    count = math.floor((t_end - t0) / window_s) - 1  # windows k = 1..count end by t_end
    if count < 1:
        return n, hit
    starts = t0 + window_s * np.arange(1, count + 1)
    valid = np.searchsorted(closes, starts - window_s, side="left") == np.searchsorted(closes, starts, side="right")
    has = (np.searchsorted(opens, starts + window_s, side="left") - np.searchsorted(opens, starts, side="left")) > 0
    seasons = season_array(starts)
    n = np.bincount(seasons[valid], minlength=4)
    hit = np.bincount(seasons[valid & has], minlength=4)
    return n, hit


@dataclass(frozen=True)
class Estimate:
    """The baseline for one incident. `p` is the value used (None when no estimate could be made)."""

    p: float | None
    source: str  # "spot" | "neighborhood" | "citywide" | "none"
    windows: int  # comparable windows at the spot in the incident's season
    p_nbr: float | None
    expected_nbr: float | None


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
        self._pooled = self._pool()
        self._estimates: dict[str, Estimate] = {}
        self._nbr_data: dict[tuple[str, str], dict] | None = None
        self.fallbacks: dict[str, int] = {"spot": 0, "neighborhood": 0, "citywide": 0, "none": 0}

    # --- same spot -------------------------------------------------------------------------------------------------
    def _groups(self) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
        """(family, spot) -> (sorted open times, sorted close times) of every non-mirror case, for the spots that have an incident."""
        needed = set(self._incident_key.values())
        opens: dict[tuple[str, str], list[float]] = defaultdict(list)
        closes: dict[tuple[str, str], list[float]] = defaultdict(list)
        for cid in sorted(self.cases):
            c = self.cases[cid]
            if cid in self.mirror:
                continue
            key = (c.type_family, spot_key(c.segment_id, c.lat, c.lon, self.params))
            if key not in needed:
                continue
            opens[key].append(c.open_utc.timestamp())
            if c.is_closed:
                closes[key].append(c.close_utc.timestamp())  # type: ignore[union-attr]
        return {k: (np.sort(np.array(opens[k])), np.sort(np.array(closes[k]))) for k in sorted(opens)}

    def _pool(self) -> dict[tuple[str, int], tuple[int, int]]:
        """Windows and hits of every spot, pooled by (family, season); season -1 pools all seasons."""
        n: dict[tuple[str, int], int] = defaultdict(int)
        h: dict[tuple[str, int], int] = defaultdict(int)
        self._group_counts: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        for key, (o, c) in self.groups.items():
            gn, gh = window_counts(o, c, self.t_end, self.window_s)
            self._group_counts[key] = (gn, gh)
            for s in range(4):
                n[(key[0], s)] += int(gn[s])
                h[(key[0], s)] += int(gh[s])
            n[(key[0], -1)] += int(gn.sum())
            h[(key[0], -1)] += int(gh.sum())
        return {k: (n[k], h[k]) for k in n}

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
        gn, gh = self._group_counts.get(key, (np.zeros(4, int), np.zeros(4, int)))
        windows = int(gn[s])
        nbr = self.nbr(inc)
        p_nbr, e_nbr = (nbr if nbr else (None, None))
        if windows >= MIN_WINDOWS:
            est = Estimate(int(gh[s]) / windows, "spot", windows, p_nbr, e_nbr)
        elif p_nbr is not None:
            est = Estimate(p_nbr, "neighborhood", windows, p_nbr, e_nbr)
        else:
            n, h = self._pooled.get((inc.type_family, s), (0, 0))
            if n < POOLED_MIN:  # too few windows for one season: pool all seasons of the family
                n, h = self._pooled.get((inc.type_family, -1), (0, 0))
            est = Estimate(h / n if n else None, "citywide" if n else "none", windows, p_nbr, e_nbr)
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

    def to_json(self) -> dict:
        return {
            "kind": self.kind, "name": self.name, "tier_set": self.tier_set, "observed": self.observed,
            "expected": self.expected, "excess": self.excess, "lo": self.lo, "hi": self.hi,
            "n_originals": self.n_originals, "expected_nbr": self.expected_nbr, "excess_nbr": self.excess_nbr,
            "n_fallback": self.n_fallback,
        }  # fmt: skip


def zombie_by_incident(zombies: list[Zombie], tier_set: TierSet) -> dict[str, Zombie]:
    """Each incident's resurrection in the tier set: headline only, or every tier (REQ-STAT-TIER.2)."""
    return {z.incident_id: z for z in zombies if tier_set == "all" or z.tier == "headline"}


def excess_rows(
    model: BaselineModel, seed: int = 311, boot: int = 1000
) -> list[ExcessRow]:
    """Observed, expected and excess by department, family and neighborhood, headline and all tiers (REQ-STAT-BASE.2).

    Originals without an estimate (no spot, neighborhood or pooled windows) are left out of the cohort and counted
    nowhere in `observed` either, so observed and expected always cover the same originals.
    """
    rng = np.random.Generator(np.random.PCG64(seed))
    rows: list[ExcessRow] = []
    for tier_set in ("headline", "all"):
        zs = zombie_by_incident(model.result.zombies, tier_set)
        groups: dict[tuple[str, str], list[tuple[float, float, float | None, bool]]] = defaultdict(list)
        for inc in eligible_originals(model.result.incidents, model.data_end, model.params, all_tiers=tier_set == "all"):
            est = model.estimate(inc)
            if est.p is None:
                continue
            row = (1.0 if inc.incident_id in zs else 0.0, est.p, est.expected_nbr, est.source != "spot")
            for kind, name in (("department", inc.department or UNKNOWN), ("family", inc.type_family),
                               ("neighborhood", inc.neighborhood or UNKNOWN)):  # fmt: skip
                groups[(kind, name)].append(row)
        for (kind, name) in sorted(groups):
            vals = groups[(kind, name)]
            obs = sum(v[0] for v in vals)
            exp = sum(v[1] for v in vals)
            nbr = [v[2] for v in vals]
            e_nbr = None if any(x is None for x in nbr) else float(sum(nbr))  # type: ignore[arg-type]
            ci = bootstrap_sum([v[0] - v[1] for v in vals], rng, boot)
            assert ci is not None
            rows.append(ExcessRow(kind, name, tier_set, int(obs), exp, obs - exp, ci[0], ci[1], len(vals), e_nbr,
                                  None if e_nbr is None else obs - e_nbr, sum(1 for v in vals if v[3])))  # fmt: skip
    return rows
