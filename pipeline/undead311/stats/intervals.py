"""Intervals for every exported rate (REQ-STAT-INT).

`wilson` is the Wilson score interval for a proportion. `bootstrap` is a percentile bootstrap with a fixed seed
(`numpy.random.Generator(PCG64(seed))`), so a rerun gives the same interval (REQ-STAT-INT.1, REQ-STAT-EXP.2).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

Z95 = 1.96
NO_CASES = "no_cases"
MIN_CLUSTERS = 10  # fewer independent spots (or pooled cells) than this and a cluster bootstrap has too few distinct resamples (ops#115)


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials; None when n = 0 (REQ-STAT-INT.2).

    The bounds are clamped to [0, 1] and widened, if floating-point error requires it, to contain k / n.
    """
    if n <= 0:
        return None
    if not 0 <= k <= n:
        raise ValueError(f"k={k} must be within 0..n={n}")
    return wilson_p(k / n, n, z)


def wilson_p(p: float, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval around a proportion `p` (which may be fractional, as for the adjusted stayed-fixed rate)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = min(1.0, max(0.0, p))
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, min(centre - half, p)), min(1.0, max(centre + half, p))


@dataclass(frozen=True)
class Rate:
    """A proportion with its Wilson interval and denominator. Null with a reason when n = 0 (REQ-STAT-INT.2)."""

    k: int
    n: int
    rate: float | None
    lo: float | None
    hi: float | None
    reason: str | None = None

    def to_json(self) -> dict:
        return {
            "rate": self.rate,
            "lo": self.lo,
            "hi": self.hi,
            "k": self.k,
            "n": self.n,
            "reason": self.reason,
        }


def make_rate(k: int, n: int, z: float = Z95) -> Rate:
    """`k / n` with a Wilson interval; `no_cases` (never 0) when n = 0 (REQ-STAT-INT.1-2)."""
    ci = wilson(k, n, z)
    if ci is None:
        return Rate(k=k, n=n, rate=None, lo=None, hi=None, reason=NO_CASES)
    return Rate(k=k, n=n, rate=k / n, lo=ci[0], hi=ci[1])


def bootstrap(
    values: Sequence[float],
    fn: Callable[[np.ndarray], float],
    seed: int,
    B: int = 1000,
    level: float = 0.95,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of `fn` over resamples of `values`; None for an empty sample (REQ-STAT-INT.1)."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return None
    rng = np.random.Generator(np.random.PCG64(seed))
    idx = rng.integers(0, arr.size, size=(B, arr.size))
    stats = np.sort(np.array([fn(arr[row]) for row in idx], dtype=float))
    tail = (1 - level) / 2
    return float(np.quantile(stats, tail)), float(np.quantile(stats, 1 - tail))


def bootstrap_sum(
    values: Sequence[float], rng: np.random.Generator, B: int = 1000, level: float = 0.95
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of the SUM of `values` (REQ-STAT-INT.1, REQ-STAT-BASE.2).

    Resamples with replacement from the caller's generator, so a sequence of calls is reproducible for one seed. The
    resamples are drawn in chunks so memory stays bounded for a large cohort. None for an empty sample.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return None
    totals = np.empty(B)
    step = max(1, 4_000_000 // arr.size)
    for lo in range(0, B, step):
        hi = min(B, lo + step)
        totals[lo:hi] = arr[rng.integers(0, arr.size, size=(hi - lo, arr.size))].sum(axis=1)
    tail = (1 - level) / 2
    return float(np.quantile(totals, tail)), float(np.quantile(totals, 1 - tail))


def _bernoulli_variance(values: np.ndarray, var: np.ndarray | None = None) -> float:
    """Variance of sum(observed_i) when each outcome is Bernoulli(p_i), from `values_i = observed_i - p_i`.

    A positive value means observed 1 (p = 1 - v), a negative one observed 0 (p = -v); a value of 0 is a certain outcome.
    That reading needs one 0/1 outcome per value. A caller whose values are means of several outcomes (the placebo's mean
    over shifted runs) passes each value's variance in `var` instead (REQ-STAT-INT.1, REQ-STAT-PLACEBO.1, ops#133)."""
    if var is not None:
        return float(np.sum(var))
    p = np.where(values > 0, 1.0 - values, -values)
    return float(np.sum(p * (1.0 - p)))


def independent_units(clusters: Sequence[int], cells: Sequence[int]) -> int:
    """Independent spots or pooled cells behind a set of originals (REQ-STAT-INT.1, ops#133).

    Originals of one spot (cluster >= 0) are one unit; originals that share a pooled estimate (cell >= 0, no spot) are one
    unit per cell; an original with neither is its own unit."""
    cl = np.asarray(clusters, dtype=int)
    ce = np.asarray(cells, dtype=int)
    spots = set(cl[cl >= 0].tolist())
    pooled = set(ce[(cl < 0) & (ce >= 0)].tolist())
    return len(spots) + len(pooled) + int(((cl < 0) & (ce < 0)).sum())


def bootstrap_sum_cells(
    values: Sequence[float],
    cells: Sequence[int],
    cell_p: Sequence[float],
    cell_n: Sequence[float],
    rng: np.random.Generator,
    B: int = 1000,
    level: float = 0.95,
    clusters: Sequence[int] | None = None,
    var: Sequence[float] | None = None,
) -> tuple[float, float] | None:
    """Bootstrap interval of a SUM whose terms each subtract an estimated chance probability (REQ-STAT-INT.1, REQ-STAT-BASE.2).

    `values[i]` is `observed_i - p_hat(cell_i)`. Two sources of error are carried:

    * `clusters[i]` is the spot an original belongs to (a negative value: its own cluster). Originals of one spot share
      the reports that make both their outcome and their p, so whole clusters are resampled, not single originals.
    * `cells[i]` is a pooled estimate shared by many originals (a negative value: none). Resampling originals alone holds
      such a p fixed, so a pooled fallback p (one number estimated from a few hundred windows and applied to thousands of
      originals) would carry no error into the interval (ops#103, S30). Each replicate also draws every pooled cell again
      as Binomial(n, p_hat) / n, which is centred on p_hat and stays in [0, 1] without clipping, so the interval always
      holds a point estimate whose cells have p_hat 0 or 1 (ops#108, S35). The replicate's sum becomes
      `sum(resampled values) + sum_c count_c * (p_hat_c - p_c)`. Cells with `cell_n <= 0` stay fixed.

    `var[i]` (optional) is the variance of value i when it is not a single 0/1 outcome minus p (the placebo's mean over runs);
    it feeds the small-spot floor. The floor applies below MIN_CLUSTERS independent spots or pooled cells (ops#133).

    Reproducible for the caller's generator; None for an empty sample.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return None
    cell_arr = np.asarray(cells, dtype=int)
    p_hat = np.asarray(cell_p, dtype=float)
    n_int = np.rint(np.asarray(cell_n, dtype=float)).astype(int)
    drawn = np.flatnonzero(n_int > 0)
    use_cells = drawn.size > 0 and bool((cell_arr >= 0).any())
    if clusters is None and not use_cells:
        return bootstrap_sum(arr, rng, B, level)
    raw = np.arange(arr.size) if clusters is None else np.asarray(clusters, dtype=int)
    labels: dict[tuple[int, int], int] = {}
    cid = np.empty(arr.size, dtype=int)
    for i, c in enumerate(raw):  # a negative label is a cluster of one
        cid[i] = labels.setdefault((int(c), 0 if c >= 0 else i), len(labels))
    n_cl = len(labels)
    cl_sum = np.bincount(cid, weights=arr, minlength=n_cl)
    if use_cells:
        slot = np.full(p_hat.size + 1, -1, dtype=int)  # the last entry answers for cell -1 (fixed)
        slot[drawn] = np.arange(drawn.size)
        sl = slot[cell_arr]
        cl_cnt = np.zeros((n_cl, drawn.size))
        keep = sl >= 0
        np.add.at(cl_cnt, (cid[keep], sl[keep]), 1.0)
        ph, nn = p_hat[drawn], n_int[drawn]
    totals = np.empty(B)
    step = max(1, min(200, 4_000_000 // (n_cl * (1 + (drawn.size if use_cells else 0)))))
    for lo in range(0, B, step):
        hi = min(B, lo + step)
        idx = rng.integers(0, n_cl, size=(hi - lo, n_cl))
        totals[lo:hi] = cl_sum[idx].sum(axis=1)
        if use_cells:
            p_draw = rng.binomial(nn, ph, size=(hi - lo, drawn.size)) / nn
            totals[lo:hi] += (cl_cnt[idx].sum(axis=1) * (ph - p_draw)).sum(axis=1)
    tail = (1 - level) / 2
    lo, hi = float(np.quantile(totals, tail)), float(np.quantile(totals, 1 - tail))
    n_units = independent_units(raw, cell_arr)
    if n_units < MIN_CLUSTERS:  # too few spots to resample: never narrower than the Bernoulli noise of the outcomes (ops#115)
        half = Z95 * math.sqrt(_bernoulli_variance(arr, None if var is None else np.asarray(var, dtype=float)))
        centre = float(arr.sum())
        lo, hi = min(lo, centre - half), max(hi, centre + half)
    return lo, hi
