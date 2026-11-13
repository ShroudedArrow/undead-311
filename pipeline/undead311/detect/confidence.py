"""Confidence score (REQ-CONF). The formula and weights are documented in docs/METHODS.md ("Confidence score") and are
pending owner approval.

confidence = clamp01(0.20*match + 0.15*gap + 0.10*specificity + 0.15*label + 0.30*baseline + 0.10*skeptic)

A term is NEUTRAL when its input is not available yet: `baseline` (0.5) until durability-stats supplies `baseline_p`,
and `skeptic` (0.5) while the verdict is `not_reviewed`. `confidence_partial` is true exactly when a term is neutral
(REQ-CONF.2). The score is never used to choose judge-mode zombies or the validation sample (REQ-CONF.3).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from undead311.detect.model import Zombie
from undead311.detect.params import DEFAULT, Params

WEIGHTS = {"match": 0.20, "gap": 0.15, "specificity": 0.10, "label": 0.15, "baseline": 0.30, "skeptic": 0.10}
LABEL_TERM = {
    "resolved": 1.0, "made_safe_temporary": 0.9, "noted": 0.8, "referred": 0.7, "planned_followup": 0.6,
    "other": 0.6, "bulk_backlog": 0.5, "invalid": 0.5, "duplicate": 0.5,
}  # fmt: skip
SKEPTIC_TERM = {"survives": 1.0, "weakened": 0.5, "explained_away": 0.0, "not_reviewed": 0.5}
NEUTRAL = 0.5
BULK_LABEL_CAP = 0.5
INHERITED_SPECIFICITY = 0.7
INTERSECTION_FACTOR = 0.9
RADIUS_FACTOR = 0.8


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class ConfidenceInputs:
    match_mode: str
    distance_m: float
    gap_days: float
    label: str
    bulk_closure: bool = False
    catch_all: bool = False
    baseline_p: float | None = None
    skeptic_verdict: str = "not_reviewed"


def match_term(mode: str, d: float, p: Params = DEFAULT) -> float:
    if mode == "segment":
        return _clamp(1 - d / (2 * p.MAX_SEGMENT_DIST))
    if mode == "intersection":
        return INTERSECTION_FACTOR * _clamp(1 - d / (2 * p.INTERSECTION_M))
    return RADIUS_FACTOR * _clamp(1 - d / p.RADIUS_M)


def terms(i: ConfidenceInputs, p: Params = DEFAULT) -> dict[str, float]:
    label = LABEL_TERM.get(i.label, LABEL_TERM["other"])
    if i.bulk_closure:
        label = min(label, BULK_LABEL_CAP)
    return {
        "match": match_term(i.match_mode, i.distance_m, p),
        "gap": _clamp(1 - i.gap_days / p.WINDOW_DAYS),
        "specificity": INHERITED_SPECIFICITY if i.catch_all else 1.0,
        "label": label,
        "baseline": NEUTRAL if i.baseline_p is None else _clamp(1 - i.baseline_p),
        "skeptic": SKEPTIC_TERM[i.skeptic_verdict],
    }


def confidence(i: ConfidenceInputs, p: Params = DEFAULT) -> tuple[float, bool]:
    """(score in [0, 1], confidence_partial)."""
    t = terms(i, p)
    score = _clamp(sum(WEIGHTS[k] * v for k, v in t.items()))
    partial = i.baseline_p is None or i.skeptic_verdict == "not_reviewed"
    return score, partial


def rescore(
    z: Zombie,
    p: Params = DEFAULT,
    *,
    catch_all: bool = False,
    baseline_p: float | None = None,
    skeptic_verdict: str | None = None,
    skeptic_notes: str | None = None,
) -> Zombie:
    """A copy of `z` with confidence recomputed from its fields and the given evidence."""
    baseline = z.baseline_p if baseline_p is None else baseline_p
    verdict = z.skeptic_verdict if skeptic_verdict is None else skeptic_verdict
    score, partial = confidence(
        ConfidenceInputs(z.match_mode, z.distance_m, z.gap_days, z.coroner_label, z.bulk_closure, catch_all, baseline, verdict),
        p,
    )
    return replace(
        z,
        baseline_p=baseline,
        skeptic_verdict=verdict,  # type: ignore[arg-type]
        skeptic_notes=z.skeptic_notes if skeptic_notes is None else skeptic_notes,
        confidence=score,
        confidence_partial=partial,
    )
