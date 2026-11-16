"""Per-tier baselines and excess, and the match-distance bands (REQ-STAT-POP, REQ-STAT-BAND; methods.md, fulldata-2).

A tier's baseline counts only the reports its re-reports can come from (the tier's population), and each tier gets its own
observed, expected and excess. Tiers are never pooled into one number.

| tier            | cohort of originals (core scope, no transferred member, not invalid/duplicate)  | chance reports counted               |
|-----------------|----------------------------------------------------------------------------------|--------------------------------------|
| headline        | label not a planned-follow-up label (H0); a planned-follow-up label (H1)         | resident legacy + new-system (H0); resident legacy only (H1) |
| source_unknown  | planned-follow-up label (a new-system re-report there is `source_unknown`)       | new-system reports                   |
| city_rereport   | label not a planned-follow-up label (a city re-report after one is not a zombie) | legacy city-originated reports       |
| sensitivity     | sensitivity-scope incidents                                                      | every report                         |

Core scope means the reports are core-scope cases too: a sensitivity-scope re-report makes a `sensitivity` zombie, so it
is no chance report for the headline. Closures of every same-family case still open a dead stretch (a closure is where any
report would show), so only the reports are filtered. Originals labeled invalid or duplicate end as a separate death and can
never be a zombie in any tier, so they are not in a cohort (a cohort chosen by label never depends on the outcome).

Match-distance bands split each original's baseline `p` by where the spot's other live reports lie relative to the original
(the empirical distance distribution of the chance reports, up to the longest distance the matching allows at that spot:
MAX_SEGMENT_DIST on a segment, RADIUS_M in a cell), and the observed zombies by their `distance_m`. The expected counts of
the bands add up to the tier's expected count. A spot with no other live report takes its family's distribution. The baseline
counts same-spot reports only, so an `intersection` match (two segments) has observed zombies and no expected count.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from undead311.detect.core import PF_LABELS, SEPARATE_LABELS, is_city_originated
from undead311.detect.model import Case, DetectionResult, Incident
from undead311.detect.params import DEFAULT, Params
from undead311.stats.baseline import (
    UNKNOWN,
    BaselineModel,
    ExcessRow,
    ExcessUnflagged,
    excess_interval,
)

TIERS = ("headline", "source_unknown", "city_rereport", "sensitivity")
BAND_EDGES = (0.0, 5.0, 15.0, 30.0)  # metres; the last band runs to the longest allowed match distance
BAND_NAMES = ("0-5 m", "5-15 m", "15-30 m", "30-75 m")
MAX_SEGMENT_DIST = 75.0


@dataclass(frozen=True)
class TierModel:
    tier: str
    tag: str  # model name, kept apart in the bootstrap (cells and spots of different populations are independent)
    model: BaselineModel


def band_of(distance_m: float) -> int:
    return int(np.searchsorted(np.array(BAND_EDGES[1:]), distance_m, side="right"))


def tier_models(
    cases: Mapping[str, Case], result: DetectionResult, params: Params = DEFAULT, data_end: datetime | None = None,
    areas: Mapping[str, float] | None = None,
) -> list[TierModel]:
    """One baseline model per (tier, label class) with the tier's population (REQ-STAT-POP.1)."""
    open_ = [i for i in result.incidents if not i.has_transferred_member and i.coroner_label not in SEPARATE_LABELS]
    core = [i for i in open_ if i.tier == "core"]
    pf = [i for i in core if i.coroner_label in PF_LABELS]
    plain = [i for i in core if i.coroner_label not in PF_LABELS]
    sens = [i for i in open_ if i.tier == "sensitivity"]

    def is_core(c: Case) -> bool:
        return c.scope_tier == "core"

    def resident(c: Case) -> bool:
        return is_core(c) and not is_city_originated(c)

    specs: list[tuple[str, str, list[Incident], object, bool]] = [
        ("headline", "headline", plain, resident, False),
        ("headline", "headline-after-planned-label", pf, lambda c: resident(c) and c.system == "legacy", False),
        ("source_unknown", "source_unknown", pf, lambda c: is_core(c) and c.system == "new", False),
        ("city_rereport", "city_rereport", plain, lambda c: is_core(c) and is_city_originated(c), False),
        ("sensitivity", "sensitivity", sens, None, True),
    ]
    return [
        TierModel(tier, tag, BaselineModel(cases, result, params, data_end, areas, incidents=incs, population=pop,  # type: ignore[arg-type]
                                           tier=tier, all_tiers=all_tiers))
        for tier, tag, incs, pop, all_tiers in specs
    ]


def _row(tm: TierModel, inc: Incident, zs: set[str]) -> tuple:
    m = tm.model
    est = m.estimate(inc)
    cell = None if est.cell is None else (tm.tag, *est.cell)
    cluster = None if est.cluster is None else (tm.tag, *est.cluster)
    return (1.0 if inc.incident_id in zs else 0.0, est.p, est.expected_nbr, est.source != "spot", cell, est.n_eff, cluster,
            m.is_bursty(inc))  # fmt: skip


def _summarize(kind: str, name: str, tier: str, vals: list[tuple], rng, rng_flag, boot: int) -> ExcessRow:
    obs, exp = sum(v[0] for v in vals), sum(v[1] for v in vals)
    nbr = [v[2] for v in vals]
    e_nbr = None if any(x is None for x in nbr) else float(sum(nbr))  # type: ignore[arg-type]
    ci = excess_interval(vals, rng, boot)
    kept = [v for v in vals if not v[7]]
    without = None
    if kept:
        k_obs, k_exp = sum(v[0] for v in kept), sum(v[1] for v in kept)
        k_ci = excess_interval(kept, rng_flag, boot)
        without = ExcessUnflagged(int(k_obs), k_exp, k_obs - k_exp, k_ci[0], k_ci[1], len(kept))
    return ExcessRow(kind, name, tier, int(obs), exp, obs - exp, ci[0], ci[1], len(vals), e_nbr,
                     None if e_nbr is None else obs - e_nbr, sum(1 for v in vals if v[3]), len(vals) - len(kept), without)  # fmt: skip


def tier_excess_rows(tms: list[TierModel], seed: int = 311, boot: int = 1000) -> list[ExcessRow]:
    """Observed, expected and excess per tier, by department, family and neighborhood, plus one `tier` row each
    (REQ-STAT-POP.2). Tiers are separate rows and never summed."""
    rng = np.random.Generator(np.random.PCG64(seed))
    rng_flag = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 1])))
    rows: list[ExcessRow] = []
    for tier in TIERS:
        groups: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        for tm in (t for t in tms if t.tier == tier):
            zs = {z.incident_id for z in tm.model.result.zombies if z.tier == tier}
            for inc in tm.model.excess_cohort("headline"):
                row = _row(tm, inc, zs)
                for kind, name in (("department", inc.department or UNKNOWN), ("family", inc.type_family),
                                   ("neighborhood", inc.neighborhood or UNKNOWN), ("tier", tier)):  # fmt: skip
                    groups[(kind, name)].append(row)
        for kind, name in sorted(groups):
            rows.append(_summarize(kind, name, tier, groups[(kind, name)], rng, rng_flag, boot))
    return rows


def band_counts(model: BaselineModel, inc: Incident) -> np.ndarray | None:
    """Other live reports of the incident's spot in each distance band from the incident (None without a spot or reports)."""
    key = model._incident_key[inc.incident_id]
    live = model._spot_info.get(key)
    geo = model._geo.get(key)
    if live is None or geo is None:
        return None
    t, xy, ids = geo
    ref = model._incident_of_case[inc.incident_id]
    mask = (t > live.t0) & live.is_live(t) & ~np.isin(ids, np.array(inc.member_ids))
    if not mask.any():
        return None
    from undead311.stats.cohort import COS_BOSTON, M_PER_DEG

    d = np.hypot(xy[mask, 0] - ref.lat * M_PER_DEG, xy[mask, 1] - ref.lon * M_PER_DEG * COS_BOSTON)
    limit = MAX_SEGMENT_DIST if key[1].startswith("seg:") else float(model.params.RADIUS_M)
    d = d[d <= limit]
    if not d.size:  # the other reports are all farther than a match allows
        return None
    return np.bincount(np.searchsorted(np.array(BAND_EDGES[1:]), d, side="right"), minlength=len(BAND_NAMES)).astype(float)


def band_shares(model: BaselineModel) -> dict[str, np.ndarray]:
    """The share of each incident's chance reports in each band; a spot without other live reports takes its family's."""
    counts = {i.incident_id: band_counts(model, i) for i in model.excess_cohort("headline")}
    fam: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(len(BAND_NAMES)))
    fam_of = {i.incident_id: i.type_family for i in model.excess_cohort("headline")}
    for iid, c in counts.items():
        if c is not None:
            fam[fam_of[iid]] += c / c.sum()
    out: dict[str, np.ndarray] = {}
    for iid, c in counts.items():
        if c is not None:
            out[iid] = c / c.sum()
        elif fam[fam_of[iid]].sum() > 0:
            out[iid] = fam[fam_of[iid]] / fam[fam_of[iid]].sum()
        else:
            out[iid] = np.full(len(BAND_NAMES), 1.0 / len(BAND_NAMES))
    return out


def band_excess_rows(tms: list[TierModel], seed: int = 311, boot: int = 1000) -> list[ExcessRow]:
    """Observed, expected and excess per tier and match-distance band (REQ-STAT-BAND.1)."""
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 2])))
    rng_flag = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 3])))
    rows: list[ExcessRow] = []
    for tier in TIERS:
        per_band: list[list[tuple]] = [[] for _ in BAND_NAMES]
        for tm in (t for t in tms if t.tier == tier):
            zd = {z.incident_id: z.distance_m for z in tm.model.result.zombies if z.tier == tier}
            shares = band_shares(tm.model)
            for inc in tm.model.excess_cohort("headline"):
                base = _row(tm, inc, set())
                hit = band_of(zd[inc.incident_id]) if inc.incident_id in zd else -1
                for b in range(len(BAND_NAMES)):
                    per_band[b].append((1.0 if b == hit else 0.0, base[1] * float(shares[inc.incident_id][b]), None, *base[3:]))
        for b, vals in enumerate(per_band):
            if vals:
                rows.append(_summarize("distance_band", BAND_NAMES[b], tier, vals, rng, rng_flag, boot))
    return rows


def mode_counts(result: DetectionResult) -> dict[str, dict[str, int]]:
    """Zombies by tier and match mode (an `intersection` match has no same-spot baseline; see the module text)."""
    out: dict[str, dict[str, int]] = {t: defaultdict(int) for t in TIERS}  # type: ignore[misc]
    for z in result.zombies:
        out[z.tier][z.match_mode] += 1
    return {t: dict(sorted(v.items())) for t, v in out.items()}


class TierBaselines:
    """`p` of an incident under the population of the tier its re-report fell in (REQ-STAT-POP.1), for `baseline_p` on
    each zombie and the adjusted stayed-fixed rate. An incident outside every tier cohort takes the pooled model's value."""

    def __init__(self, tms: list[TierModel], result: DetectionResult, pooled: BaselineModel) -> None:
        self.pooled = pooled
        self.tier_of = {z.incident_id: z.tier for z in result.zombies}
        self.by_tier: dict[str, dict[str, BaselineModel]] = defaultdict(dict)
        for tm in tms:
            for inc in tm.model.incidents:
                self.by_tier[tm.tier][inc.incident_id] = tm.model

    def p(self, inc: Incident, tier: str | None = None) -> float | None:
        tier = tier or self.tier_of.get(inc.incident_id, "headline")
        model = self.by_tier.get(tier, {}).get(inc.incident_id)
        got = model.p(inc) if model is not None else None
        return got if got is not None else self.pooled.p(inc)

    def zombie_baselines(self) -> dict[str, float]:
        by_inc = {i.incident_id: i for i in self.pooled.result.incidents}
        out: dict[str, float] = {}
        for z in self.pooled.result.zombies:
            p = self.p(by_inc[z.incident_id], z.tier)
            if p is not None:
                out[z.zombie_id] = min(1.0, max(0.0, p))
        return out
