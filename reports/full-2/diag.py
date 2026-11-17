"""Read-only diagnosis of the headline placebo / excess (no pipeline code is changed)."""
import json
import sys
from collections import defaultdict

import duckdb
import numpy as np

sys.path.insert(0, "pipeline")
from undead311.detect.cases import cases_from_table
from undead311.detect.core import detect
from undead311.detect.edges import sql_edges
from undead311.detect.params import DEFAULT as P
from undead311.stats.cohort import COS_BOSTON, M_PER_DEG
from undead311.stats.pipeline import neighborhood_geometry
from undead311.stats.tiers import tier_models

con = duckdb.connect(".local-data/data/processed/undead311.duckdb"  # run from the repo root with DATA_DIR set as for run_full.py, read_only=True)
cases = cases_from_table(con, "cases_clean")
by = {c.id: c for c in cases}
edges = sql_edges(con, cases, P)
res = detect(cases, P, edges)
areas, _ = neighborhood_geometry(con)
tms = tier_models(by, res, P, None, areas)
head = next(t for t in tms if t.tag == "headline")
m = head.model
zs = {z.incident_id for z in res.zombies if z.tier == "headline"}
cohort = m.excess_cohort("headline")
print("cohort", len(cohort), "observed", sum(i.incident_id in zs for i in cohort))

rows = defaultdict(lambda: dict(n=0, obs=0, p=0.0, p_adj=0.0))
for inc in cohort:
    est = m.estimate(inc)
    key = m._incident_key[inc.incident_id]
    kind = "segment" if key[1].startswith("seg:") else "cell"
    dense = m.is_dense(key)
    limit = P.MAX_SEGMENT_DIST if kind == "segment" else P.RADIUS_M
    geo = m._geo.get(key)
    live = m._spot_info.get(key)
    share = 1.0
    if geo is not None and live is not None:
        t, xy, ids = geo
        mask = (t > live.t0) & live.is_live(t) & ~np.isin(ids, np.array(inc.member_ids))
        if mask.any():
            ref = m._incident_of_case[inc.incident_id]
            d = np.hypot(xy[mask, 0] - ref.lat * M_PER_DEG, xy[mask, 1] - ref.lon * M_PER_DEG * COS_BOSTON)
            share = float((d <= limit).mean())
    for name in (f"{kind}/{'dense' if dense else 'sparse'}/{est.source}", f"{kind}/all", "ALL"):
        r = rows[name]
        r["n"] += 1
        r["obs"] += inc.incident_id in zs
        r["p"] += est.p
        r["p_adj"] += est.p * share
print(f"{'group':34s} {'n':>7} {'obs':>7} {'exp':>9} {'exp*share<=limit':>17}")
for k in sorted(rows):
    r = rows[k]
    print(f"{k:34s} {r['n']:>7} {r['obs']:>7} {r['p']:>9.1f} {r['p_adj']:>17.1f}  excess {r['obs'] - r['p']:>9.1f} -> {r['obs'] - r['p_adj']:>9.1f}")

# the cohort's source_unknown tier: how many originals could have had a new-system re-report at all
su = next(t for t in tms if t.tier == "source_unknown")
from datetime import datetime, timedelta, timezone

new_start = datetime(2025, 8, 1, tzinfo=timezone.utc)
inc = su.model.incidents
elig = [i for i in inc if i.close_utc + timedelta(days=P.WINDOW_DAYS) > new_start]
print("source_unknown cohort", len(inc), "closed late enough for a new-system re-report", len(elig))
