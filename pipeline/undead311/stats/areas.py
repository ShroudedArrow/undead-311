"""Match areas (REQ-STAT-AREA; methods.md "Primary baseline").

The same-spot baseline estimates each original's chance of a coincidental report from the history of **its own match area**:
the same-family reports that would count as a match for it. A report matches an incident when it matches any member under the
location rule of the detector (`detect.match.match`): the same segment within MAX_SEGMENT_DIST, the intersection rule, or
RADIUS_M when one of the two is not snapped (and RADIUS_M for every pair in `radius` matching). The first full-data runs used the
whole segment or the whole 60 m cell as the area, which credited reports that the detector can never match (full-2: the headline
cohort's expected count fell 17% when each `p` was weighted by the share of the spot within the match distance).

`MatchAreas` finds, for each incident, the non-mirror same-family cases that match any of its members (the members themselves
included). It uses a KD-tree per family for candidates and the exact `match` for the decision, so the area is the detector's own
rule. Areas are stored as row numbers into per-case arrays, and identical areas share one number, so a model can keep one
live-time record per area. One `MatchAreas` is built per detection result and shared by every tier model.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping

import numpy as np
from scipy.spatial import cKDTree

from undead311.detect.match import match
from undead311.detect.model import Case, Incident
from undead311.detect.params import DEFAULT, Params
from undead311.stats.cohort import spot_key

M_PER_DEG = 111_320.0
MARGIN_M = 3.0  # the tree works in a flat metre grid; the exact rule decides, so the margin only has to cover its distortion


def _xy(c: Case) -> tuple[float, float]:
    return c.lat * M_PER_DEG, c.lon * M_PER_DEG * math.cos(math.radians(c.lat))


class MatchAreas:
    """Match areas of a set of incidents (REQ-STAT-AREA.1) and the per-case arrays the baseline reads them through."""

    def __init__(
        self,
        cases: Mapping[str, Case],
        incidents: Iterable[Incident],
        mirror_ids: frozenset[str] | set[str] = frozenset(),
        params: Params = DEFAULT,
    ) -> None:
        self.params = params
        self.case_ids = sorted(cases)
        self.row = {cid: i for i, cid in enumerate(self.case_ids)}
        n = len(self.case_ids)
        self.open_ts = np.empty(n)
        self.close_ts = np.full(n, np.nan)
        self.x = np.empty(n)
        self.y = np.empty(n)
        self.is_mirror = np.zeros(n, dtype=bool)
        self.spot_idx = np.empty(n, dtype=np.int64)
        self.spot_keys: list[tuple[str, str]] = []
        spot_index: dict[tuple[str, str], int] = {}
        for i, cid in enumerate(self.case_ids):
            c = cases[cid]
            self.open_ts[i] = c.open_utc.timestamp()
            if c.is_closed:
                self.close_ts[i] = c.close_utc.timestamp()  # type: ignore[union-attr]
            self.x[i], self.y[i] = _xy(c)
            self.is_mirror[i] = cid in mirror_ids
            sk = (c.type_family, spot_key(c.segment_id, c.lat, c.lon, params))
            self.spot_idx[i] = spot_index.setdefault(sk, len(spot_index))
            if self.spot_idx[i] == len(self.spot_keys):
                self.spot_keys.append(sk)
        by_family: dict[str, list[int]] = defaultdict(list)
        for i, cid in enumerate(self.case_ids):
            if not self.is_mirror[i]:
                by_family[cases[cid].type_family].append(i)
        trees = {fam: (cKDTree(np.column_stack([self.x[r], self.y[r]])), np.array(r)) for fam, r in by_family.items()}
        radius = params.max_match_dist_m + MARGIN_M
        self.rows: list[np.ndarray] = []  # area number -> sorted row numbers
        self.family: list[str] = []
        self.of_incident: dict[str, int] = {}
        intern: dict[tuple[str, bytes], int] = {}
        for inc in sorted(incidents, key=lambda i: i.incident_id):
            members = [m for m in inc.member_ids if m not in mirror_ids]
            area = {self.row[m] for m in members}
            tree, tree_rows = trees.get(inc.type_family, (None, None))
            if tree is not None:
                for mid in members:
                    member = cases[mid]
                    for j in tree.query_ball_point((self.x[self.row[mid]], self.y[self.row[mid]]), r=radius):
                        r = int(tree_rows[j])
                        if r in area:
                            continue
                        if match(member, cases[self.case_ids[r]], params) is not None:
                            area.add(r)
            arr = np.array(sorted(area), dtype=np.int64)
            k = (inc.type_family, arr.tobytes())
            a = intern.get(k)
            if a is None:
                a = intern[k] = len(self.rows)
                self.rows.append(arr)
                self.family.append(inc.type_family)
            self.of_incident[inc.incident_id] = a

    def ids(self, a: int) -> list[str]:
        return [self.case_ids[r] for r in self.rows[a]]
