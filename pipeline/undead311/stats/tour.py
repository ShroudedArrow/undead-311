"""Provisional judge-mode tour (REQ-STAT-TOUR.1).

Three headline zombies the Skeptic has not explained away: the owner's override
(`data/labels/judge_tour_override.json`) when it names exactly three such zombies, else a ranking. The ranking takes the
Skeptic's "survives" zombies first and uses "weakened" ones only to fill when fewer than three survive (owner decision,
ops#215; the card shows the Skeptic's note); "not_reviewed" ones fill last, which only happens before a Skeptic pass.
Within a verdict, most re-reports first, ties by zombie ID. The provisional ranking only counts resident-reported zombies (headline tier, which
leaves out city re-reports and planned follow-ups) whose re-report opened at least `MIN_TOUR_GAP_HOURS` after the closure
(owner decision, ops#44: a re-report seconds after a closure is a crew's work log, not a resurrection to show). The confidence
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
MIN_TOUR_GAP_HOURS = 1.0  # ops#44: the provisional ranking skips re-reports that opened sooner than this after the closure
# ops#215: the order verdicts fill the tour in. "explained_away" is never featured (filtered before ranking).
VERDICT_RANK = {"survives": 0, "weakened": 1, "not_reviewed": 2}


@dataclass(frozen=True)
class JudgeTour:
    provisional: bool
    zombie_ids: tuple[str, ...]
    source: Literal["override", "most_reports"]
    # how the three were confirmed: "field" (two raters on the street), "records" (record-confirmed: the re-report's closure
    # says it was repaired again; REQ-STAT-VAL.5) or None while provisional
    confirmation: Literal["field", "records"] | None = None

    def to_json(self, data_version: str, params: Params = DEFAULT, dataset: str = "full") -> dict:
        return {
            "data_version": data_version, "dataset": dataset, "params": params_json(params), "provisional": self.provisional,
            "seed": None, "zombie_ids": list(self.zombie_ids), "source": self.source, "confirmation": self.confirmation,
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


def build_tour(
    zombies: Iterable[Zombie], override: list[str] | None = None, confirmed: Iterable[str] | None = None,
    confirmation: Literal["field", "records"] = "field",
) -> JudgeTour | None:
    """The tour, or None when fewer than three headline zombies exist (REQ-STAT-TOUR.1, .2).

    With at least three confirmed zombie IDs (REQ-STAT-VAL.3) the tour is `provisional: false` and uses only confirmed
    zombies: the owner's override if every listed ID is confirmed, else the confirmed ones with the most re-reports.
    Fewer than three confirmed IDs leaves the tour provisional (a tour needs three). `confirmation` says what confirmed them
    ("field" or "records", recorded in the tour file and shown on the site as record-confirmed for "records").

    An override is used only if it lists exactly three distinct headline zombies; otherwise it is ignored. A zombie the
    Skeptic explained away is never featured, in the override or the ranking (REQ-SKEP, ops#45).
    The ranking puts "survives" before "weakened" before "not_reviewed" (ops#215), then most re-reports, ties by ID.
    """
    headline = {z.zombie_id: z for z in zombies if z.tier == "headline" and z.skeptic_verdict != "explained_away"}
    sure = {i for i in (confirmed or ()) if i in headline}
    if len(sure) >= TOUR_SIZE:
        headline = {i: z for i, z in headline.items() if i in sure}
        provisional = False
    else:
        provisional = True
    named = override is not None and len(override) == TOUR_SIZE and len(set(override)) == TOUR_SIZE
    if named and all(i in headline for i in override):  # type: ignore[union-attr]
        return JudgeTour(provisional, tuple(override), "override", None if provisional else confirmation)  # type: ignore[arg-type]
    if len(headline) < TOUR_SIZE:
        return None
    if provisional or confirmation == "records":  # a field check needs no filter (ops#44); a records check has no one on the street
        headline = {i: z for i, z in headline.items() if z.gap_days * 24.0 >= MIN_TOUR_GAP_HOURS and not z.city_rereport}
        if len(headline) < TOUR_SIZE:
            return None
    ranked = sorted(headline.values(), key=lambda z: (VERDICT_RANK.get(z.skeptic_verdict, 3), -z.reports_after, z.zombie_id))
    return JudgeTour(provisional, tuple(z.zombie_id for z in ranked[:TOUR_SIZE]), "most_reports", None if provisional else confirmation)
