"""Shift test and placebo calibration (REQ-STAT-SHIFT, REQ-STAT-PLACEBO).

Shift test: each spot's closure times are moved by one random offset (circularly, inside the spot's observed span, with
locations fixed), the candidate count is redone, and this is repeated `runs` times (default 1,000) with a fixed seed. The
count is the number of eligible headline-scope originals that have at least one same-family report (not a mirror copy) opened
within WINDOW_DAYS after the closure (the incident's own member reports are never counted, ops#102). It is the detector's candidate rule without
attribution, tiers or planned follow-ups, so `observed` (the same count with no shift) is the number the shifted counts
are comparable with. The detector's own headline count is exported beside it as `headline_zombies`.

Placebo: for the first PLACEBO_RUNS shifts, the same-spot baseline (REQ-STAT-BASE.1) is recomputed on the shifted closures.
Each original's placebo excess is its mean (shifted hit minus baseline) over the runs; the exported `excess` is their sum
and `lo`/`hi` a seeded bootstrap 95% interval over originals, the same kind of interval the observed excess carries. Closures are moved away from the
reports they may have caused, so the placebo excess should be near zero; when its interval excludes 0 the
`calibration_warning` flag is set. Originals that used a neighborhood or citywide fallback keep their unshifted value.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from undead311.stats.baseline import BaselineModel, season_array, season_integrated_p
from undead311.stats.cohort import eligible_originals, season_idx, spot_key
from undead311.stats.intervals import MIN_CLUSTERS, bootstrap_sum_cells, independent_units

SHIFT_RUNS = 1000
PLACEBO_RUNS = 10
CHUNK = 50  # shifted runs held in memory at once


@dataclass(frozen=True)
class ShiftResult:
    runs: int
    seed: int
    observed: int
    mean: float
    q025: float
    q975: float
    headline_zombies: int
    counts: tuple[int, ...]

    def to_json(self) -> dict:
        return {
            "runs": self.runs, "seed": self.seed, "observed": self.observed, "mean": self.mean,
            "q025": self.q025, "q975": self.q975, "headline_zombies": self.headline_zombies,
        }  # fmt: skip


@dataclass(frozen=True)
class PlaceboResult:
    runs: int
    excess: float
    lo: float
    hi: float
    calibration_warning: bool

    def to_json(self) -> dict:
        return {
            "excess": self.excess, "lo": self.lo, "hi": self.hi, "runs": self.runs,
            "calibration_warning": self.calibration_warning,
        }  # fmt: skip


@dataclass
class _Spots:
    """Flat arrays over the eligible originals and their spots (one row per incident, one group per spot and family)."""

    keys: list[tuple[str, str]]
    group_of: np.ndarray  # incident -> group index
    close: np.ndarray  # incident close, epoch s
    season: np.ndarray
    t0: np.ndarray  # per group: first report
    length: np.ndarray  # per group: circle length = (data end - first report) - WINDOW
    is_zombie: np.ndarray
    p_fixed: np.ndarray  # baseline of the incident from the model (used for fallbacks and as the unshifted value)
    spot_based: np.ndarray  # incident used its own spot's windows
    cell: list  # per incident: the pooled estimate its fixed baseline came from (None when it is not pooled)
    n_eff: np.ndarray  # per incident: windows behind that pooled estimate
    k_after: np.ndarray  # per incident and season: other live reports of its spot (unshifted closures)
    days: np.ndarray  # per group and season: live days of the spot (unshifted closures)
    big: float
    opens_flat: np.ndarray  # reports of every group, encoded with the group's offset, globally sorted
    own_inc: np.ndarray  # the incident's own member reports that are in the group: incident row ...
    own_open: np.ndarray  # ... and the member's open time, encoded like opens_flat
    own_raw: np.ndarray  # ... and the same time as epoch seconds


def _build(model: BaselineModel) -> _Spots | None:
    incs = list(eligible_originals(model.incidents, model.data_end, model.params, all_tiers=model.all_tiers))
    zs = {z.incident_id for z in model.result.zombies if z.tier == model.tier}
    keys = sorted({model._incident_key[i.incident_id] for i in incs})
    keys = [k for k in keys if k in model.groups]
    if not incs or not keys:
        return None
    index = {k: g for g, k in enumerate(keys)}
    incs = [i for i in incs if model._incident_key[i.incident_id] in index]
    t_end = model.t_end
    t_min = min(float(model.groups[k][0][0]) for k in keys)
    big = (t_end - t_min) + 10 * model.window_s + 1.0
    t0 = np.array([model.groups[k][0][0] for k in keys])
    length = np.maximum((t_end - t0) - model.window_s, 1.0)
    est = [model.estimate(i) for i in incs]
    flat = np.concatenate([model.groups[k][0] - t_min + g * big for g, k in enumerate(keys)])
    own_inc: list[int] = []
    own_open: list[float] = []
    own_raw: list[float] = []
    for row, inc in enumerate(incs):
        g = index[model._incident_key[inc.incident_id]]
        for cid in inc.member_ids:
            c = model.cases[cid]
            in_group = cid not in model.mirror and (c.type_family, spot_key(c.segment_id, c.lat, c.lon, model.params)) == keys[g]
            if in_group:  # only members that the group's open times contain are left out of a count
                own_inc.append(row)
                own_open.append(c.open_utc.timestamp() - t_min + g * big)
                own_raw.append(c.open_utc.timestamp())
    info = [model._spot_info[k] for k in keys]
    k_after = np.array([info[index[model._incident_key[i.incident_id]]].counts - model.own_after(i) for i in incs])
    return _Spots(
        keys, np.array([index[model._incident_key[i.incident_id]] for i in incs]),
        np.array([i.close_utc.timestamp() for i in incs]),
        np.array([season_idx(i.close_utc) for i in incs]), t0, length,
        np.array([i.incident_id in zs for i in incs]), np.array([e.p if e.p is not None else 0.0 for e in est]),
        np.array([e.source == "spot" for e in est]), [e.cell for e in est], np.array([e.n_eff for e in est]),
        k_after, np.array([i.days for i in info]), big, flat, np.array(own_inc, dtype=int), np.array(own_open),
        np.array(own_raw),
    )  # fmt: skip


def _hits(sp: _Spots, t_min: float, window_s: float, shifted_close: np.ndarray) -> np.ndarray:
    """Per incident and run: 1 when another report opens in (close, close + WINDOW_DAYS]. Shape (incidents, runs).

    The incident's own members are left out (REQ-STAT-SHIFT.1, REQ-STAT-PLACEBO.1). Unshifted they open before the
    closure, so they never fall in the window; a shifted closure moved ahead of them would count the very reports that
    made the incident and push the chance count up by 13-17% in sparse spots (ops#102, S29)."""
    base = sp.group_of[:, None] * sp.big - t_min
    lo = np.searchsorted(sp.opens_flat, base + shifted_close, side="right")
    hi = np.searchsorted(sp.opens_flat, base + shifted_close + window_s, side="right")
    found = (hi - lo).astype(float)
    if sp.own_inc.size:
        q = base[sp.own_inc] + shifted_close[sp.own_inc]
        inside = (sp.own_open[:, None] > q) & (sp.own_open[:, None] <= q + window_s)
        for r in range(found.shape[1]):
            found[:, r] -= np.bincount(sp.own_inc, weights=inside[:, r], minlength=found.shape[0])
    return (found > 0.5).astype(int)


def shift_and_placebo(
    model: BaselineModel, seed: int = 311, runs: int = SHIFT_RUNS, placebo_runs: int = PLACEBO_RUNS
) -> tuple[ShiftResult | None, PlaceboResult | None]:
    """The shift distribution and the placebo excess (REQ-STAT-SHIFT.1-2, REQ-STAT-PLACEBO.1-2). Deterministic for a seed."""
    sp = _build(model)
    zombies = sum(1 for z in model.result.zombies if z.tier == model.tier)
    if sp is None:
        return None, None
    t_min = min(float(model.groups[k][0][0]) for k in sp.keys)
    w = model.window_s
    observed = int(_hits(sp, t_min, w, sp.close[:, None]).sum())
    rng = np.random.Generator(np.random.PCG64(seed))
    counts: list[int] = []
    kept = np.empty((len(sp.keys), 0))
    done = 0
    while done < runs:
        r = min(CHUNK, runs - done)
        delta = rng.random((len(sp.keys), r)) * sp.length[:, None]
        if done == 0:
            kept = delta[:, :placebo_runs].copy()
        g = sp.group_of
        shifted = sp.t0[g][:, None] + np.mod(sp.close[:, None] - sp.t0[g][:, None] + delta[g], sp.length[g][:, None])
        counts.extend(int(x) for x in _hits(sp, t_min, w, shifted).sum(axis=0))
        done += r
    arr = np.array(counts, dtype=float)
    shift = ShiftResult(
        runs, seed, observed, float(arr.mean()), float(np.quantile(arr, 0.025)), float(np.quantile(arr, 0.975)),
        zombies, tuple(counts),
    )  # fmt: skip
    return shift, _placebo(model, sp, kept[:, : min(placebo_runs, kept.shape[1])], t_min, seed)


def _placebo(model: BaselineModel, sp: _Spots, delta: np.ndarray, t_min: float, seed: int) -> PlaceboResult | None:
    """Placebo excess over the shifted runs, with a bootstrap interval (REQ-STAT-PLACEBO.1-2)."""
    n_runs = delta.shape[1]
    if n_runs == 0:
        return None
    w = model.window_s
    g = sp.group_of
    shifted = sp.t0[g][:, None] + np.mod(sp.close[:, None] - sp.t0[g][:, None] + delta[g], sp.length[g][:, None])
    hits = _hits(sp, t_min, w, shifted)
    expected = np.tile(sp.p_fixed[:, None], (1, n_runs))  # fallbacks keep their unshifted value
    for gi, key in enumerate(sp.keys):
        rows = np.flatnonzero((g == gi) & sp.spot_based)
        if rows.size == 0:
            continue
        opens, closes = model.groups[key]  # every closure starts a dead stretch, as in the baseline (ops#112, ops#113)
        own_sel = np.flatnonzero(np.isin(sp.own_inc, rows))
        local = np.searchsorted(rows, sp.own_inc[own_sel])  # position of each own member's incident among `rows`
        own_t = sp.own_raw[own_sel]
        own_s = season_array(own_t)
        for run in range(n_runs):
            moved = np.sort(sp.t0[gi] + np.mod(closes - sp.t0[gi] + delta[gi, run], sp.length[gi]))
            live = model.live_spot(opens, moved)  # the spot's live time with its closures moved
            mine = np.zeros((rows.size, 4))
            ok_own = (own_t > live.t0) & live.is_live(own_t)
            np.add.at(mine, (local[ok_own], own_s[ok_own]), 1.0)
            # the excess's own estimator on the moved closure: the days of its window in each season against the spot's live
            # reports and days of that season (REQ-STAT-BASE.1, REQ-STAT-PLACEBO.1, ops#111)
            if model.is_dense(key):  # dense spots use the same sliding-window share as the excess (ops#131)
                share = model.dense_share(opens, live)
                seas = season_array(shifted[rows, run])
                got = np.where(np.isnan(share[seas]), share[4], share[seas])
                if not np.isnan(got).any():
                    expected[rows, run] = got
                    continue
            k = np.maximum(live.counts[None, :] - mine, 0.0)
            expected[rows, run] = season_integrated_p(k, live.days, model.window_season_days(shifted[rows, run]))
    per_incident = (hits - expected).mean(axis=1)  # each original's mean (hit - baseline) over the shifted runs
    mean = float(per_incident.sum())
    # the baseline's own error (ops#103): originals share the draw of the pooled estimate their baseline came from, and
    # the originals of one spot are resampled together
    cell_ids: dict[tuple, int] = {}
    cells = np.full(per_incident.size, -1, dtype=int)
    for row in range(per_incident.size):
        key = sp.cell[row]
        if key is not None:
            cells[row] = cell_ids.setdefault(key, len(cell_ids))
    cell_p = np.zeros(len(cell_ids))
    cell_n = np.zeros(len(cell_ids))
    for c in range(len(cell_ids)):
        members = np.flatnonzero(cells == c)
        cell_p[c] = float(expected[members].mean())
        cell_n[c] = float(sp.n_eff[members[0]])
    clusters = np.where(sp.spot_based, g, -1)
    p_bar = np.clip(expected.mean(axis=1), 0.0, 1.0)  # each value is a mean of n_runs outcomes: variance p(1 - p) / n_runs
    ci = bootstrap_sum_cells(
        per_incident, cells, cell_p, cell_n, np.random.Generator(np.random.PCG64(seed + 1)), clusters=clusters,
        var=p_bar * (1.0 - p_bar) / n_runs,
    )
    if ci is None:
        return None
    n_clusters = independent_units(clusters, cells)
    # a handful of spots says nothing about calibration: no warning below MIN_CLUSTERS (ops#115)
    return PlaceboResult(n_runs, mean, ci[0], ci[1], bool((ci[0] > 0 or ci[1] < 0) and n_clusters >= MIN_CLUSTERS))
