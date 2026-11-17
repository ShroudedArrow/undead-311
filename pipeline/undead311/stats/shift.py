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
from undead311.stats.cohort import eligible_originals, season_idx
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
    """Flat arrays over the eligible originals, their match areas and the spots whose closures move (REQ-STAT-SHIFT.1).

    One row per incident. Reports are read from the incident's match area (`area_of`); closures move with the offset of the spot
    they belong to (`spot_of` for the incident's own closure, `close_spots` for the closures inside an area), so the closures of
    one spot keep their order and spacing."""

    areas: list[tuple[str, str]]  # distinct area keys of the incidents
    area_of: np.ndarray  # incident -> area index
    spot_of: np.ndarray  # incident -> local spot index of its own closure
    close: np.ndarray  # incident close, epoch s
    season: np.ndarray
    t0: np.ndarray  # per local spot: first report of the population
    length: np.ndarray  # per local spot: circle length = (data end - first report) - WINDOW
    movable: np.ndarray  # per local spot: has a report of the population, so its closures can move
    is_zombie: np.ndarray
    p_fixed: np.ndarray  # baseline of the incident from the model (used for fallbacks and as the unshifted value)
    spot_based: np.ndarray  # incident used its own area's windows
    cell: list  # per incident: the pooled estimate its fixed baseline came from (None when it is not pooled)
    n_eff: np.ndarray  # per incident: windows behind that pooled estimate
    k_after: np.ndarray  # per incident and season: other live reports of its area (unshifted closures)
    days: np.ndarray  # per area and season: live days of the area (unshifted closures)
    big: float
    opens_flat: np.ndarray  # reports of every area, encoded with the area's offset, globally sorted
    own_inc: np.ndarray  # the incident's own member reports that are in the area: incident row ...
    own_open: np.ndarray  # ... and the member's open time, encoded like opens_flat
    own_raw: np.ndarray  # ... and the same time as epoch seconds
    close_spots: list[np.ndarray]  # per area: local spot index of each closure (aligned with `model.groups[area][1]`)
    n_spots: int
    cluster: np.ndarray  # incident -> bootstrap cluster (its own spot)


def _build(model: BaselineModel) -> _Spots | None:
    incs = list(eligible_originals(model.incidents, model.data_end, model.params, all_tiers=model.all_tiers))
    zs = {z.incident_id for z in model.result.zombies if z.tier == model.tier}
    incs = [i for i in incs if model._incident_key[i.incident_id] in model.groups]
    if not incs:
        return None
    ar = model.areas
    akeys = sorted({model._incident_key[i.incident_id] for i in incs}, key=lambda k: model._area_no[k])
    aindex = {k: n for n, k in enumerate(akeys)}
    # local spots: the own spot of every incident and the spot of every closure inside the areas
    glob = {int(g) for k in akeys for g in model._close_spots[k]}
    own_glob = [int(ar.spot_idx[ar.row[model._incident_of_case[i.incident_id].id]]) for i in incs]
    glob |= set(own_glob)
    spots = sorted(glob, key=lambda g: ar.spot_keys[g])  # by (family, spot key): the order of the seeded draws is stable
    local = {g: n for n, g in enumerate(spots)}
    usable = model._pop & ~ar.is_mirror
    first = np.full(int(ar.spot_idx.max()) + 1, np.inf)
    np.minimum.at(first, ar.spot_idx[usable], ar.open_ts[usable])
    t0g = first[np.array(spots)]
    movable = np.isfinite(t0g)
    t0 = np.where(movable, t0g, 0.0)
    t_end = model.t_end
    t_min = float(min(model.groups[k][0][0] for k in akeys))
    big = (t_end - t_min) + 10 * model.window_s + 1.0
    length = np.maximum((t_end - t0) - model.window_s, 1.0)
    est = [model.estimate(i) for i in incs]
    flat = np.concatenate([model.groups[k][0] - t_min + a * big for a, k in enumerate(akeys)])
    own_inc: list[int] = []
    own_open: list[float] = []
    own_raw: list[float] = []
    for row, inc in enumerate(incs):
        a = aindex[model._incident_key[inc.incident_id]]
        for cid in inc.member_ids:
            if cid not in model.mirror and model.in_population(cid):  # members are in the area; those of the population are its reports
                t = model.cases[cid].open_utc.timestamp()
                own_inc.append(row)
                own_open.append(t - t_min + a * big)
                own_raw.append(t)
    info = [model._spot_info[k] for k in akeys]
    area_of = np.array([aindex[model._incident_key[i.incident_id]] for i in incs])
    k_after = np.array([info[area_of[r]].counts - model.own_after(i) for r, i in enumerate(incs)])
    spot_of = np.array([local[g] for g in own_glob])
    return _Spots(
        akeys, area_of, spot_of, np.array([i.close_utc.timestamp() for i in incs]),
        np.array([season_idx(i.close_utc) for i in incs]), t0, length, movable,
        np.array([i.incident_id in zs for i in incs]), np.array([e.p if e.p is not None else 0.0 for e in est]),
        np.array([e.source == "spot" for e in est]), [e.cell for e in est], np.array([e.n_eff for e in est]),
        k_after, np.array([i.days for i in info]), big, np.sort(flat), np.array(own_inc, dtype=int), np.array(own_open),
        np.array(own_raw), [np.array([local[int(g)] for g in model._close_spots[k]], dtype=int) for k in akeys], len(spots), spot_of,
    )  # fmt: skip


def _hits(sp: _Spots, t_min: float, window_s: float, shifted_close: np.ndarray) -> np.ndarray:
    """Per incident and run: 1 when another report opens in (close, close + WINDOW_DAYS] in its match area. Shape (incidents, runs).

    The incident's own members are left out (REQ-STAT-SHIFT.1, REQ-STAT-PLACEBO.1). Unshifted they open before the
    closure, so they never fall in the window; a shifted closure moved ahead of them would count the very reports that
    made the incident and push the chance count up by 13-17% in sparse spots (ops#102, S29)."""
    base = sp.area_of[:, None] * sp.big - t_min
    lo = np.searchsorted(sp.opens_flat, base + shifted_close, side="right")
    hi = np.searchsorted(sp.opens_flat, base + shifted_close + window_s, side="right")
    found = (hi - lo).astype(float)
    if sp.own_inc.size:
        q = base[sp.own_inc] + shifted_close[sp.own_inc]
        inside = (sp.own_open[:, None] > q) & (sp.own_open[:, None] <= q + window_s)
        for r in range(found.shape[1]):
            found[:, r] -= np.bincount(sp.own_inc, weights=inside[:, r], minlength=found.shape[0])
    return (found > 0.5).astype(int)


def _move(sp: _Spots, close: np.ndarray, spot: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """Closures moved circularly inside their spot's observed span by that spot's offset; a spot with no report stays put."""
    t0, ln = sp.t0[spot], sp.length[spot]
    moved = t0 + np.mod(close - t0 + delta[spot], ln)
    return np.where(sp.movable[spot], moved, close)


def _shifted(sp: _Spots, delta: np.ndarray) -> np.ndarray:
    """Each incident's own closure after the shift: shape (incidents, runs)."""
    return np.stack([_move(sp, sp.close, sp.spot_of, delta[:, r]) for r in range(delta.shape[1])], axis=1)


def shift_and_placebo(
    model: BaselineModel, seed: int = 311, runs: int = SHIFT_RUNS, placebo_runs: int = PLACEBO_RUNS
) -> tuple[ShiftResult | None, PlaceboResult | None]:
    """The shift distribution and the placebo excess (REQ-STAT-SHIFT.1-2, REQ-STAT-PLACEBO.1-2). Deterministic for a seed."""
    sp = _build(model)
    zombies = sum(1 for z in model.result.zombies if z.tier == model.tier)
    if sp is None:
        return None, None
    t_min = float(min(model.groups[k][0][0] for k in sp.areas))
    w = model.window_s
    observed = int(_hits(sp, t_min, w, sp.close[:, None]).sum())
    rng = np.random.Generator(np.random.PCG64(seed))
    counts: list[int] = []
    kept = np.empty((sp.n_spots, 0))
    done = 0
    while done < runs:
        r = min(CHUNK, runs - done)
        delta = rng.random((sp.n_spots, r)) * sp.length[:, None]
        if done == 0:
            kept = delta[:, :placebo_runs].copy()
        counts.extend(int(x) for x in _hits(sp, t_min, w, _shifted(sp, delta)).sum(axis=0))
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
    shifted = _shifted(sp, delta)
    hits = _hits(sp, t_min, w, shifted)
    expected = np.tile(sp.p_fixed[:, None], (1, n_runs))  # fallbacks keep their unshifted value
    for ai, key in enumerate(sp.areas):
        rows = np.flatnonzero((sp.area_of == ai) & sp.spot_based)
        if rows.size == 0:
            continue
        opens, closes = model.groups[key]  # every closure starts a dead stretch, as in the baseline (ops#112, ops#113)
        own_sel = np.flatnonzero(np.isin(sp.own_inc, rows))
        local = np.searchsorted(rows, sp.own_inc[own_sel])  # position of each own member's incident among `rows`
        own_t = sp.own_raw[own_sel]
        own_s = season_array(own_t)
        dense = model.is_dense(key)
        for run in range(n_runs):
            moved = np.sort(_move(sp, closes, sp.close_spots[ai], delta[:, run]))
            live = model.live_spot(opens, moved)  # the area's live time with its closures moved
            mine = np.zeros((rows.size, 4))
            ok_own = (own_t > live.t0) & live.is_live(own_t)
            np.add.at(mine, (local[ok_own], own_s[ok_own]), 1.0)
            # the excess's own estimator on the moved closure: the days of its window in each season against the area's live
            # reports and days of that season (REQ-STAT-BASE.1, REQ-STAT-PLACEBO.1, ops#111)
            if dense:  # dense areas use the same sliding-window share as the excess (ops#131)
                share = model.dense_share(opens, live)
                seas = season_array(shifted[rows, run])
                got = np.where(np.isnan(share[seas]), share[4], share[seas])
                if not np.isnan(got).any():
                    expected[rows, run] = got
                    continue
            k = np.maximum(live.counts[None, :] - mine, 0.0)
            expected[rows, run] = season_integrated_p(k, live.days, model.window_season_days(shifted[rows, run]))
    per_incident = (hits - expected).mean(axis=1)  # each original's mean (shifted hit minus baseline) over the shifted runs
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
    clusters = np.where(sp.spot_based, sp.cluster, -1)
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
