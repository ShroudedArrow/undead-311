"""Provisional judge-mode tour (REQ-STAT-TOUR.1).

Three headline zombies the Skeptic has not explained away: the owner's override
(`data/labels/judge_tour_override.json`) when it names exactly three such zombies, else the three with the most
re-reports, ties by zombie ID. The confidence
score is never read, so the tour cannot be tuned by it (design property P10). `provisional` is true until the
confirmed validation set exists (REQ-STAT-TOUR.2, a credibility task).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from undead311.detect.model import Zombie
from undead311.detect.params import DEFAULT, Params
from undead311.stats.meta import params_json

TOUR_SIZE = 3


@dataclass(frozen=True)
class JudgeTour:
    provisional: bool
    zombie_ids: tuple[str, ...]
    source: Literal["override", "most_reports"]

    def to_json(self, data_version: str, params: Params = DEFAULT, dataset: str = "full") -> dict:
        return {
            "data_version": data_version, "dataset": dataset, "params": params_json(params), "provisional": self.provisional,
            "seed": None, "zombie_ids": list(self.zombie_ids), "source": self.source,
        }  # fmt: skip


def read_override(path: Path) -> list[str] | None:
    """Zombie IDs from the owner's override file: a JSON list, or an object with `zombie_ids`. None if absent or bad."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return None
    ids = data.get("zombie_ids") if isinstance(data, dict) else data
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        return None
    return ids


def build_tour(zombies: Iterable[Zombie], override: list[str] | None = None) -> JudgeTour | None:
    """The provisional tour, or None when fewer than three headline zombies exist (REQ-STAT-TOUR.1).

    An override is used only if it lists exactly three distinct headline zombies; otherwise it is ignored. A zombie the
    Skeptic explained away is never featured, in the override or the ranking (REQ-SKEP, ops#45).
    """
    headline = {z.zombie_id: z for z in zombies if z.tier == "headline" and z.skeptic_verdict != "explained_away"}
    named = override is not None and len(override) == TOUR_SIZE and len(set(override)) == TOUR_SIZE
    if named and all(i in headline for i in override):  # type: ignore[union-attr]
        return JudgeTour(True, tuple(override), "override")  # type: ignore[arg-type]
    if len(headline) < TOUR_SIZE:
        return None
    ranked = sorted(headline.values(), key=lambda z: (-z.reports_after, z.zombie_id))
    return JudgeTour(True, tuple(z.zombie_id for z in ranked[:TOUR_SIZE]), "most_reports")
