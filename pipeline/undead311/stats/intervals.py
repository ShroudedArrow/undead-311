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
    p = k / n
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
