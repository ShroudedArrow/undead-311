"""The baseline term of the confidence score (REQ-CONF.1-2, REQ-SKEP.1).

durability-stats (REQ-STAT-BASE.4) computes `baseline_p` per zombie: the local chance that a same-family report appears
at the same place within the window by coincidence, from the same-spot baseline. The stats stage exposes it through an
optional function `zombie_baselines(con, result, cases, params) -> {zombie_id: baseline_p}` in `undead311.stats.pipeline`.
`apply_baselines` stores the values on the zombies and rescores them. A zombie without a value keeps the neutral
baseline term and `confidence_partial = true`; with a value and a Skeptic review, the score is complete.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from undead311.detect.confidence import rescore
from undead311.detect.model import Zombie
from undead311.detect.params import DEFAULT, Params


class BadBaseline(ValueError):
    """A `baseline_p` outside [0, 1] (or not a number): a contract violation by the stats stage, never clamped silently."""


def apply_baselines(
    zombies: Iterable[Zombie], baselines: Mapping[str, float] | None, p: Params = DEFAULT
) -> list[Zombie]:
    """Zombies with `baseline_p` set and the confidence rescored; zombies without a value are returned unchanged."""
    zombies = list(zombies)
    if not baselines:
        return zombies
    for zid, value in baselines.items():
        if not isinstance(value, int | float) or isinstance(value, bool) or math.isnan(value) or not 0.0 <= value <= 1.0:
            raise BadBaseline(f"baseline_p for {zid} is {value!r}; it must be a number in [0, 1]")
    return [rescore(z, p, baseline_p=float(baselines[z.zombie_id])) if z.zombie_id in baselines else z for z in zombies]
