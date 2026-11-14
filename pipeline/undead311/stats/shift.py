"""Shift test and placebo calibration (REQ-STAT-SHIFT, REQ-STAT-PLACEBO).

Shift test: each spot's closure times are moved by one random offset (circularly, inside the spot's observed span, with
locations fixed), the candidate count is redone, and this is repeated `runs` times (default 1,000) with a fixed seed. The
count is the number of eligible headline-scope originals that have at least one same-family report (not a mirror copy) opened
within WINDOW_DAYS after the closure. It is the detector's candidate rule without
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

from undead311.stats.baseline import MIN_WINDOWS, BaselineModel, season_array, window_counts
from undead311.stats.cohort import eligible_originals, season_idx
from undead311.stats.intervals import bootstrap_sum

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
    big: float
    opens_flat: np.ndarray  # reports of every group, encoded with the group's offset, globally sorted


def _build(model: BaselineModel) -> _Spots | None:
    incs = list(eligible_originals(model.result.incidents, model.data_end, model.params))
    zs = {z.incident_id for z in model.result.zombies if z.tier == "headline"}
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
    return _Spots(
        keys, np.array([index[model._incident_key[i.incident_id]] for i in incs]),
        np.array([i.close_utc.timestamp() for i in incs]),
        np.array([season_idx(i.close_utc) for i in incs]), t0, length,
        np.array([i.incident_id in zs for i in incs]), np.array([e.p if e.p is not None else 0.0 for e in est]),
        np.array([e.source == "spot" for e in est]), big, flat,
    )  # fmt: skip


def _hits(sp: _Spots, t_min: float, window_s: float, shifted_close: np.ndarray) -> np.ndarray:
    """Per incident and run: 1 when a report opens in (close, close + WINDOW_DAYS]. Shape (incidents, runs).

    The incident's own members are not excluded: unshifted they open before the closure, so they never fall in the window;
    shifted, the closure is just a random time, and counting every report is the null the baseline windows also use."""
    base = sp.group_of[:, None] * sp.big - t_min
    lo = np.searchsorted(sp.opens_flat, base + shifted_close, side="right")
    hi = np.searchsorted(sp.opens_flat, base + shifted_close + window_s, side="right")
    return ((hi - lo) > 0).astype(int)


def shift_and_placebo(
    model: BaselineModel, seed: int = 311, runs: int = SHIFT_RUNS, placebo_runs: int = PLACEBO_RUNS
) -> tuple[ShiftResult | None, PlaceboResult | None]:
    """The shift distribution and the placebo excess (REQ-STAT-SHIFT.1-2, REQ-STAT-PLACEBO.1-2). Deterministic for a seed."""
    sp = _build(model)
    zombies = sum(1 for z in model.result.zombies if z.tier == "headline")
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
    expected = np.tile(sp.p_fixed[:, None], (1, n_runs))
    for gi, key in enumerate(sp.keys):
        opens, closes = model.groups[key]
        rows = np.flatnonzero((g == gi) & sp.spot_based)
        if rows.size == 0:
            continue
        for run in range(n_runs):
            moved = np.sort(sp.t0[gi] + np.mod(closes - sp.t0[gi] + delta[gi, run], sp.length[gi]))
            n, h = window_counts(opens, moved, model.t_end, w)
            s = season_array(shifted[rows, run])  # the season of the moved closure
            ok = n[s] >= MIN_WINDOWS
            expected[rows[ok], run] = h[s[ok]] / n[s[ok]]
    per_incident = (hits - expected).mean(axis=1)  # each original's mean (hit - baseline) over the shifted runs
    mean = float(per_incident.sum())
    ci = bootstrap_sum(per_incident, np.random.Generator(np.random.PCG64(seed + 1)))
    if ci is None:
        return None
    return PlaceboResult(n_runs, mean, ci[0], ci[1], bool(ci[0] > 0 or ci[1] < 0))
