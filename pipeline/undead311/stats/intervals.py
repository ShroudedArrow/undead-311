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


def bootstrap_sum_cells(
    values: Sequence[float],
    cells: Sequence[int],
    cell_p: Sequence[float],
    cell_n: Sequence[float],
    rng: np.random.Generator,
    B: int = 1000,
    level: float = 0.95,
) -> tuple[float, float] | None:
    """Bootstrap interval of a SUM whose terms each subtract an estimated chance probability (REQ-STAT-INT.1, REQ-STAT-BASE.2).

    `values[i]` is `observed_i - p_hat(cell_i)`. Resampling originals alone holds every p fixed, so a pooled fallback p
    (one number estimated from a few hundred windows and applied to thousands of originals) would carry no error into the
    interval (ops#103, S30). Here each replicate also draws every cell's p again from Beta(p n + 1, (1 - p) n + 1), the
    posterior of its `cell_n` comparable windows, re-centred on the estimate and clipped to [0, 1], and the replicate's sum
    becomes `sum(resampled values) + sum_c count_c * (p_hat_c - p_c)`. Cells with `cell_n <= 0` (and `cells[i] < 0`) stay
    fixed. Reproducible for the caller's generator; None for an empty sample.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return None
    cell_arr = np.asarray(cells, dtype=int)
    p_hat = np.asarray(cell_p, dtype=float)
    n_eff = np.asarray(cell_n, dtype=float)
    drawn = np.flatnonzero(n_eff > 0)
    if drawn.size == 0 or not (cell_arr >= 0).any():
        return bootstrap_sum(arr, rng, B, level)
    a = p_hat[drawn] * n_eff[drawn] + 1.0
    b = (1.0 - p_hat[drawn]) * n_eff[drawn] + 1.0
    centre = a / (a + b)
    slot = np.full(p_hat.size + 1, -1, dtype=int)  # the last entry answers for cell -1 (fixed)
    slot[drawn] = np.arange(drawn.size)
    totals = np.empty(B)
    step = max(1, min(200, 4_000_000 // arr.size))
    for lo in range(0, B, step):
        hi = min(B, lo + step)
        idx = rng.integers(0, arr.size, size=(hi - lo, arr.size))
        totals[lo:hi] = arr[idx].sum(axis=1)
        p_draw = np.clip(rng.beta(a, b, size=(hi - lo, drawn.size)) - centre + p_hat[drawn], 0.0, 1.0)
        for r in range(hi - lo):
            sl = slot[cell_arr[idx[r]]]  # the drawn-cell slot of each resampled original (-1 when fixed)
            sl = sl[sl >= 0]
            count = np.bincount(sl, minlength=drawn.size)
            totals[lo + r] += float((count * (p_hat[drawn] - p_draw[r])).sum())
    tail = (1 - level) / 2
    return float(np.quantile(totals, tail)), float(np.quantile(totals, 1 - tail))
