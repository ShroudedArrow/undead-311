"""Fair comparisons: shrinkage, funnel limits and reporting intensity (REQ-STAT-EB, REQ-STAT-FUNNEL, REQ-STAT-REP).

Unit: an eligible original (cohort.py). A group's rate is the share of its originals that became a possible zombie in the
tier set (the resurrection rate; lower is better). `k` is the number of those originals and `n` the number of originals.

* Shrinkage (REQ-STAT-EB.1): beta-binomial with prior mean mu fixed at the citywide rate and concentration kappa fitted by
  maximum marginal likelihood (method of moments when the likelihood has no interior maximum). The posterior mean
  `(k + mu*kappa) / (n + kappa)` is `w*raw + (1-w)*mu` with `w = n / (n + kappa)` in [0, 1], so it lies between the raw and
  the citywide rate. The interval is the 95% posterior interval of that rate (widened to contain it).
* Funnel limits (REQ-STAT-FUNNEL.1): exact binomial quantiles of Bin(n, mu) / n at 0.025 / 0.975 (95%) and 0.001 / 0.999
  (99.8%). A group is `unusual` only when its raw rate is outside the 99.8% limits (REQ-STAT-FUNNEL.2).
* Reporting intensity (REQ-STAT-REP.1): in-scope reports opened in a neighborhood per km of SAM street, per family. It is a
  floor on what happens (a zombie needs someone to report again). A neighborhood group is exported only with its intensity
  (REQ-STAT-REP.2).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import optimize
from scipy import stats as sps

from undead311.detect.model import Case, DetectionResult
from undead311.detect.params import DEFAULT, Params
from undead311.stats.cohort import eligible_originals
from undead311.stats.intervals import wilson

KAPPA_MIN, KAPPA_MAX = 1e-2, 1e7
UNKNOWN = "(unknown)"
DENSE_UP_TO = 500  # funnel limits are exported for every n up to this, then on a geometric ladder to the largest n
LADDER = 1.03


def fit_kappa(ks: Sequence[int], ns: Sequence[int], mu: float) -> tuple[float, str]:
    """(kappa, method) for groups (k_i of n_i) with prior mean `mu` (REQ-STAT-EB.1).

    Maximum marginal likelihood over log kappa; when the likelihood is maximal at an edge (no between-group variation,
    or too little data) the method-of-moments value is used instead.
    """
    k = np.asarray(ks, float)
    n = np.asarray(ns, float)
    usable = n > 0
    k, n = k[usable], n[usable]
    if n.size < 2 or mu <= 0.0 or mu >= 1.0:
        return KAPPA_MAX, "degenerate"

    def nll(log_kappa: float) -> float:
        kappa = math.exp(log_kappa)
        return -float(sps.betabinom.logpmf(k, n, mu * kappa, (1 - mu) * kappa).sum())

    lo, hi = math.log(KAPPA_MIN), math.log(KAPPA_MAX)
    res = optimize.minimize_scalar(nll, bounds=(lo, hi), method="bounded", options={"xatol": 1e-6})
    if res.success and lo + 1e-3 < res.x < hi - 1e-3:
        return float(math.exp(res.x)), "ml"
    p = k / n
    s2 = float(np.sum(n * (p - mu) ** 2) / np.sum(n))  # n-weighted variance of the raw rates around mu
    between = s2 - mu * (1 - mu) / float(n.mean())
    kappa = KAPPA_MAX if between <= 1e-12 else mu * (1 - mu) / between - 1.0
    return float(min(KAPPA_MAX, max(KAPPA_MIN, kappa))), "moments"


def shrink(k: int, n: int, mu: float, kappa: float) -> float:
    """Posterior mean of a group's rate: between its raw rate and `mu` (REQ-STAT-EB.1, property P4)."""
    if n <= 0:
        return mu
    raw = k / n
    value = (k + mu * kappa) / (n + kappa)
    return min(max(raw, mu), max(min(raw, mu), value))  # exact bound against float rounding


def posterior_interval(k: int, n: int, mu: float, kappa: float, level: float = 0.95) -> tuple[float, float]:
    a, b = mu * kappa + k, (1 - mu) * kappa + n - k
    tail = (1 - level) / 2
    lo, hi = float(sps.beta.ppf(tail, a, b)), float(sps.beta.ppf(1 - tail, a, b))
    mean = shrink(k, n, mu, kappa)
    return max(0.0, min(lo, mean)), min(1.0, max(hi, mean))


def funnel_limits_at(n: int, p0: float) -> tuple[float, float, float, float]:
    """(lo95, hi95, lo998, hi998) rate limits for n cases around p0, from exact binomial quantiles (REQ-STAT-FUNNEL.1)."""
    q = sps.binom.ppf([0.025, 0.975, 0.001, 0.999], n, p0) / n
    return tuple(float(min(1.0, max(0.0, x))) for x in q)  # type: ignore[return-value]


def funnel_ns(n_max: int) -> list[int]:
    """The sample sizes the limits are exported for: every n up to DENSE_UP_TO, then a 3% ladder to `n_max`."""
    ns = list(range(1, min(n_max, DENSE_UP_TO) + 1))
    n = float(DENSE_UP_TO)
    while n_max > DENSE_UP_TO and n < n_max:
        n = max(n + 1, n * LADDER)
        ns.append(int(min(n, n_max)))
    return sorted(set(ns))


def funnel_limits(p0: float | None, n_max: int) -> list[dict]:
    if p0 is None or n_max < 1:
        return []
    out = []
    for n in funnel_ns(n_max):
        lo95, hi95, lo998, hi998 = funnel_limits_at(n, p0)
        out.append({"n": n, "lo95": lo95, "hi95": hi95, "lo998": lo998, "hi998": hi998})
    return out


@dataclass(frozen=True)
class Group:
    kind: str
    name: str
    n: int
    k: int
    raw: float | None
    shrunk: float | None
    lo: float | None
    hi: float | None
    unusual: bool
    reports_per_km: float | None
    raw_lo: float | None = None
    raw_hi: float | None = None

    def to_json(self) -> dict:
        return {
            "kind": self.kind, "name": self.name, "n": self.n, "k": self.k, "raw": self.raw, "shrunk": self.shrunk,
            "lo": self.lo, "hi": self.hi, "unusual": self.unusual, "reports_per_km": self.reports_per_km,
            "raw_lo": self.raw_lo, "raw_hi": self.raw_hi,
        }  # fmt: skip


def group_counts(
    result: DetectionResult, data_end, params: Params = DEFAULT, *, tier_set: str = "headline"
) -> dict[tuple[str, str], tuple[int, int]]:
    """(k, n) per (kind, name) over the eligible originals of the tier set (REQ-STAT-EB)."""
    zs = {z.incident_id for z in result.zombies if tier_set == "all" or z.tier == "headline"}
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for inc in eligible_originals(result.incidents, data_end, params, all_tiers=tier_set == "all"):
        hit = inc.incident_id in zs
        for key in (("department", inc.department or UNKNOWN), ("family", inc.type_family),
                    ("neighborhood", inc.neighborhood or UNKNOWN)):  # fmt: skip
            counts[key][0] += hit
            counts[key][1] += 1
    return {k: (v[0], v[1]) for k, v in sorted(counts.items())}


def build_groups(
    counts: Mapping[tuple[str, str], tuple[int, int]], intensity: Mapping[str, float] | None = None
) -> tuple[float | None, float | None, list[Group]]:
    """(citywide rate, kappa, groups) from (k, n) counts (REQ-STAT-EB, REQ-STAT-FUNNEL.2, REQ-STAT-REP.2).

    The citywide rate is taken over the family groups, which partition the originals. Neighborhood groups without a
    reports-per-km value are left out.
    """
    fam = [v for (kind, _), v in counts.items() if kind == "family"]
    total_n = sum(n for _, n in fam)
    mu = sum(k for k, _ in fam) / total_n if total_n else None
    if mu is None:
        return None, None, []
    items = [(key, v) for key, v in counts.items() if v[1] > 0]
    kappa, _method = fit_kappa([v[0] for _, v in items], [v[1] for _, v in items], mu)
    out: list[Group] = []
    for (kind, name), (k, n) in items:
        per_km = None
        if kind == "neighborhood":
            per_km = (intensity or {}).get(name)
            if per_km is None:
                continue
        raw = k / n
        _lo95, _hi95, lo998, hi998 = funnel_limits_at(n, mu)
        s = shrink(k, n, mu, kappa)
        lo, hi = posterior_interval(k, n, mu, kappa)
        w = wilson(k, n)
        out.append(Group(kind, name, n, k, raw, s, lo, hi, bool(raw < lo998 or raw > hi998), per_km,
                         w[0] if w else None, w[1] if w else None))  # fmt: skip
    return mu, kappa, out


def intensity_by_neighborhood(cases: Mapping[str, Case], street_km: Mapping[str, float]) -> dict[str, float]:
    """In-scope reports opened per km of street, by neighborhood (REQ-STAT-REP.1). Missing or zero street length: absent."""
    n: dict[str, int] = defaultdict(int)
    for c in cases.values():
        if c.neighborhood:
            n[c.neighborhood] += 1
    return {name: n[name] / km for name, km in sorted(street_km.items()) if km and km > 0 and name in n}


def intensity_by_family(cases: Mapping[str, Case], street_km: Mapping[str, float]) -> list[dict]:
    """Reports per km of street per neighborhood and family (REQ-STAT-REP.1)."""
    n: dict[tuple[str, str], int] = defaultdict(int)
    for c in cases.values():
        if c.neighborhood:
            n[(c.neighborhood, c.type_family)] += 1
    return [
        {"neighborhood": nb, "family": fam, "reports": cnt, "reports_per_km": cnt / street_km[nb]}
        for (nb, fam), cnt in sorted(n.items())
        if street_km.get(nb)
    ]


def groups_payload(
    result: DetectionResult, cases: Mapping[str, Case], data_end, data_version: str, params: Params, dataset: str,
    street_km: Mapping[str, float] | None = None,
) -> tuple[dict, dict]:
    """(`groups.json`, `funnel.json`) payloads, each with the headline groups and, beside them, the all-tier groups
    (REQ-STAT-TIER.1)."""
    from undead311.stats.meta import params_json

    intensity = intensity_by_neighborhood(cases, street_km or {})
    head: dict = {"data_version": data_version, "dataset": dataset, "params": params_json(params), "seed": None}
    sets = {}
    for tier_set in ("headline", "all"):
        mu, kappa, groups = build_groups(group_counts(result, data_end, params, tier_set=tier_set), intensity)
        sets[tier_set] = (mu, kappa, [g.to_json() for g in groups])
    mu, kappa, groups = sets["headline"]
    mu_all, kappa_all, groups_all = sets["all"]
    note = None if street_km else "reports per km are unavailable without the neighborhood boundaries and SAM segments"
    groups_file = {
        **head, "citywide": mu, "kappa": kappa, "groups": groups, "all_tiers": {
            "citywide": mu_all, "kappa": kappa_all, "groups": groups_all},
        "intensity": intensity_by_family(cases, street_km or {}), "intensity_note": note,
    }  # fmt: skip
    n_max = max((g["n"] for g in groups + groups_all), default=0)
    funnel_file = {
        **head, "citywide": mu, "limits": funnel_limits(mu, n_max), "groups": groups,
        "all_tiers": {"citywide": mu_all, "limits": funnel_limits(mu_all, n_max), "groups": groups_all},
    }  # fmt: skip
    return groups_file, funnel_file
