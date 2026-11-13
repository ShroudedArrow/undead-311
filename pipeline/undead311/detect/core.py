"""The detector: a pure function `detect(cases, p, edges) -> DetectionResult` (zombie-definition.md steps 2-9).

Steps (each cites its requirement):
1. Incidents (REQ-DET-1): closed in-scope cases in (open UTC, ID) order join an incident only if they match a
   member's location and family, opened strictly before the incident's earliest member close, and keep the span
   within INCIDENT_MAX_SPAN_DAYS. Otherwise they start a new incident. The incident's close time is its latest member
   close, its Coroner label is that member's label (ties by smallest member ID), its ID is its smallest member ID.
2. Candidate pairs (REQ-DET-2): (incident I, case R) with R opening strictly after I's close and within WINDOW_DAYS,
   same family, R matching a member, R not a member. Excluded by reason: `mirror` (R is a cross-system copy of a
   closed case opened within MIRROR_WINDOW_HOURS), `transferred_original` (a member is a transfer closure or a
   Transitioned closure), `linked_successor` (R continues a member as its linked successor).
3. Attribution (REQ-DET-3): R in (open UTC, ID) order attaches to the eligible incident with the latest close
   (ties by smallest incident ID). The earliest attached R is the resurrection.
4. Classification (REQ-DET-PF, REQ-DET-SEP) and tiers (REQ-DET-TIER).
5. Chains (REQ-DET-CHAIN).
The same code path serves the test town, the property tests and the full data.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from undead311.detect.confidence import rescore
from undead311.detect.edges import brute_edges
from undead311.detect.match import better
from undead311.detect.model import (
    Case,
    Chain,
    DetectionResult,
    Incident,
    Match,
    PlannedFollowup,
    SeparateDeath,
    Tier,
    Zombie,
)
from undead311.detect.params import DEFAULT, Params
from undead311.ingest.closure_flags import is_mirror_pair, is_transferred_original

CITY_SOURCES = frozenset({"Employee Generated", "City Worker App", "Maximo Integration"})
PF_LABELS = frozenset({"made_safe_temporary", "referred", "planned_followup"})
SEPARATE_LABELS = frozenset({"invalid", "duplicate"})
EXCLUSION_REASONS = ("mirror", "transferred_original", "linked_successor")

Edges = dict[tuple[str, str], Match]


@dataclass
class _Inc:
    """Mutable incident under construction."""

    members: list[Case] = field(default_factory=list)

    @property
    def id(self) -> str:
        return min(m.id for m in self.members)

    @property
    def family(self) -> str:
        return self.members[0].type_family

    @property
    def min_open(self) -> datetime:
        return min(m.open_utc for m in self.members)

    @property
    def min_close(self) -> datetime:
        return min(m.close_utc for m in self.members)  # type: ignore[type-var]

    @property
    def max_close(self) -> datetime:
        return max(m.close_utc for m in self.members)  # type: ignore[type-var]

    @property
    def closer(self) -> Case:
        """Latest-closing member; ties by smallest ID (REQ-DET-1.3)."""
        return min(self.members, key=lambda m: (-m.close_utc.timestamp(), m.id))  # type: ignore[union-attr]


def _adjacency(edges: Edges) -> dict[str, list[tuple[str, Match]]]:
    adj: dict[str, list[tuple[str, Match]]] = defaultdict(list)
    for (a, b), m in sorted(edges.items()):
        adj[a].append((b, m))
        adj[b].append((a, m))
    return adj


def build_incidents(cases: list[Case], adj: dict[str, list[tuple[str, Match]]], p: Params) -> tuple[list[_Inc], dict[str, _Inc]]:
    """Greedy incident pass (REQ-DET-1.1-1.4). Returns incidents and member id -> incident."""
    span = timedelta(days=p.INCIDENT_MAX_SPAN_DAYS)
    incs: list[_Inc] = []
    of: dict[str, _Inc] = {}
    for c in sorted((c for c in cases if c.is_closed), key=lambda c: (c.open_utc, c.id)):
        best: _Inc | None = None
        for nid, _m in adj.get(c.id, ()):
            inc = of.get(nid)
            if inc is None or inc.family != c.type_family:
                continue
            if not c.open_utc < inc.min_close:  # REQ-DET-1.4: opened before the incident's first closure
                continue
            if max(inc.max_close, c.close_utc) - min(inc.min_open, c.open_utc) > span:  # type: ignore[type-var]
                continue
            if best is None or inc.id < best.id:
                best = inc
        if best is None:
            best = _Inc()
            incs.append(best)
        best.members.append(c)
        of[c.id] = best
    return incs, of


def _finalize_incident(inc: _Inc) -> Incident:
    rep = min(inc.members, key=lambda m: (m.open_utc, m.id))
    closer = inc.closer
    return Incident(
        incident_id=inc.id,
        member_ids=tuple(sorted(m.id for m in inc.members)),
        type_family=inc.family,
        close_utc=closer.close_utc,  # type: ignore[arg-type]
        coroner_label=closer.coroner_label or "other",
        department=rep.department,
        neighborhood=rep.neighborhood,
        district=rep.district,
        segment_id=rep.segment_id,
        bulk_closure=closer.bulk_closure,
        has_transferred_member=any(
            is_transferred_original(
                {"system": m.system, "closure_text": m.closure_text, "closure_code": m.closure_code}
            )
            for m in inc.members
        ),
        tier="sensitivity" if any(m.scope_tier == "sensitivity" for m in inc.members) else "core",
    )


def mirror_ids(cases: list[Case], adj: dict[str, list[tuple[str, Match]]], p: Params) -> frozenset[str]:
    """Cases that are a cross-system copy of a closed in-scope case opened within MIRROR_WINDOW_HOURS (REQ-DET-2.4)."""
    by_id = {c.id: c for c in cases}
    out = set()
    for c in cases:
        for nid, _ in adj.get(c.id, ()):
            n = by_id[nid]
            if n.is_closed and _mirror(c, n, p):
                out.add(c.id)
                break
    return frozenset(out)


def _mirror(a: Case, b: Case, p: Params) -> bool:
    """Cross-system, same family, opened within MIRROR_WINDOW_HOURS (REQ-DET-2.4); location is the edge's match."""
    if p.MIRROR_WINDOW_HOURS != DEFAULT.MIRROR_WINDOW_HOURS:
        return a.system != b.system and abs((a.open_utc - b.open_utc).total_seconds()) <= p.MIRROR_WINDOW_HOURS * 3600
    return is_mirror_pair(a.system, b.system, a.open_utc, b.open_utc, a.type_family == b.type_family, True)


def candidate_pairs(
    cases: list[Case], p: Params = DEFAULT, edges: Edges | None = None
) -> set[tuple[str, str]]:
    """Case-level candidate pairs (original m, re-report R): R opens strictly after m's close, within WINDOW_DAYS,
    same family, matching location. Before incident grouping and exclusions (property P3, REQ-DET-2.1)."""
    cases = [c for c in cases if c.scope_tier in ("core", "sensitivity")]
    edges = brute_edges(cases, p) if edges is None else edges
    by_id = {c.id: c for c in cases}
    win = timedelta(days=p.WINDOW_DAYS)
    out = set()
    for a, b in edges:
        for m, r in ((by_id[a], by_id[b]), (by_id[b], by_id[a])):
            if m.is_closed and m.close_utc < r.open_utc <= m.close_utc + win:  # type: ignore[operator]
                out.add((m.id, r.id))
    return out


def detect(cases: list[Case], p: Params = DEFAULT, edges: Edges | None = None) -> DetectionResult:
    """Run steps 1-5 on in-scope cases. `edges` may be precomputed (SQL); otherwise brute force is used."""
    cases = sorted((c for c in cases if c.scope_tier in ("core", "sensitivity")), key=lambda c: c.id)
    result = DetectionResult(excluded_pairs=dict.fromkeys(EXCLUSION_REASONS, 0))
    if not cases:
        return result
    edges = brute_edges(cases, p) if edges is None else edges
    adj = _adjacency(edges)

    # 1. incidents
    incs, of = build_incidents(cases, adj, p)
    incs.sort(key=lambda i: i.id)
    result.incidents = [_finalize_incident(i) for i in incs]
    final = {i.incident_id: i for i in result.incidents}

    # 2-3. candidate pairs and attribution
    mirrors = mirror_ids(cases, adj, p)
    result.mirror_ids = mirrors
    win = timedelta(days=p.WINDOW_DAYS)
    attached: dict[str, list[Case]] = defaultdict(list)
    best_match: dict[tuple[str, str], Match] = {}
    for r in sorted(cases, key=lambda c: (c.open_utc, c.id)):
        pairs: dict[str, Match] = {}
        for nid, m in adj.get(r.id, ()):
            inc = of.get(nid)
            if inc is None or inc.family != r.type_family:
                continue
            iid = inc.id
            fin = final[iid]
            if not (fin.close_utc < r.open_utc <= fin.close_utc + win) or r.id in fin.member_ids:
                continue
            pairs[iid] = better(pairs[iid], m) if iid in pairs else m
        eligible: list[str] = []
        for iid, m in sorted(pairs.items()):
            fin = final[iid]
            if r.id in mirrors:
                reason = "mirror"
            elif fin.has_transferred_member:
                reason = "transferred_original"
            elif set(r.predecessor_ids) & set(fin.member_ids):
                reason = "linked_successor"
            else:
                eligible.append(iid)
                best_match[(iid, r.id)] = m
                continue
            result.excluded_pairs[reason] += 1
        if eligible:
            target = min(eligible, key=lambda i: (-final[i].close_utc.timestamp(), i))
            attached[target].append(r)
            result.attribution[r.id] = target

    # 4. classification and tiers
    pending: list[tuple[Incident, Case, int, bool, bool, Tier, Match]] = []
    by_id = {c.id: c for c in cases}
    for iid in sorted(attached):
        inc, rs = final[iid], attached[iid]
        res = rs[0]
        if inc.coroner_label in SEPARATE_LABELS:
            result.separate_deaths.append(
                SeparateDeath(iid, inc.coroner_label, res.id, inc.type_family, inc.department)  # type: ignore[arg-type]
            )
            continue
        after_temp = source_unknown = False
        if inc.coroner_label in PF_LABELS:
            if res.system == "legacy":
                if res.source in CITY_SOURCES or res.city_originated_type:
                    result.planned_followups.append(PlannedFollowup(iid, res.id))
                    continue
                after_temp = inc.coroner_label == "made_safe_temporary"
            else:
                source_unknown = True
        if inc.tier == "sensitivity" or res.scope_tier == "sensitivity":
            tier: Tier = "sensitivity"
        elif source_unknown:
            tier = "source_unknown"
        else:
            tier = "headline"
        pending.append((inc, res, len(rs), after_temp, source_unknown, tier, best_match[(iid, res.id)]))

    # 5. chains: zombie incident -> the incident its closed resurrection belongs to
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    has_incoming: set[str] = set()
    for inc, res, *_ in pending:
        find(inc.incident_id)
        nxt = of.get(res.id)
        if nxt is not None and res.is_closed:
            find(nxt.id)
            parent[find(nxt.id)] = find(inc.incident_id)
            has_incoming.add(nxt.id)
    comps: dict[str, list[str]] = defaultdict(list)
    for iid in list(parent):
        comps[find(iid)].append(iid)
    zombie_inc = {inc.incident_id: tier for inc, _, _, _, _, tier, _ in pending}
    chain_of: dict[str, Chain] = {}
    for members in comps.values():
        starts = [i for i in members if i not in has_incoming] or members
        start = min(starts, key=lambda i: (final[i].close_utc, i))
        zs = [i for i in members if i in zombie_inc]
        chain = Chain(
            chain_id=start,
            incident_ids=tuple(sorted(members)),
            times_risen=len(zs),
            headline_count=sum(1 for i in zs if zombie_inc[i] == "headline"),
        )
        for i in members:
            chain_of[i] = chain
        if zs:
            result.chains.append(chain)
    result.chains.sort(key=lambda c: c.chain_id)

    for inc, res, n_after, after_temp, source_unknown, tier, m in pending:
        chain = chain_of[inc.incident_id]
        z = Zombie(
                incident_id=inc.incident_id,
                member_ids=inc.member_ids,
                resurrection_id=res.id,
                reports_after=n_after,
                gap_days=(res.open_utc - inc.close_utc).total_seconds() / 86400,
                match_mode=m.mode,
                distance_m=m.distance_m,
                tier=tier,
                after_temporary_fix=after_temp,
                source_unknown=source_unknown,
                chain_id=chain.chain_id,
                times_risen=chain.times_risen,
                type_family=inc.type_family,
                coroner_label=inc.coroner_label,
                bulk_closure=inc.bulk_closure,
                close_year=inc.close_utc.year,
                department=inc.department,
                neighborhood=inc.neighborhood,
                district=inc.district,
                segment_id=inc.segment_id,
                catch_all=res.catch_all or any(by_id[mid].catch_all for mid in inc.member_ids),
            )
        result.zombies.append(rescore(z, p))
    result.zombies.sort(key=lambda z: z.zombie_id)
    result.planned_followups.sort(key=lambda z: (z.incident_id, z.resurrection_id))
    result.separate_deaths.sort(key=lambda z: (z.incident_id, z.rereport_id))
    return result


__all__ = ["build_incidents", "candidate_pairs", "detect", "mirror_ids"]
