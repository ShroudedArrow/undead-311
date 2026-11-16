"""Field validation of possible zombies: sample, precision, agreement and the confirmed set (REQ-STAT-VAL, REQ-STAT-TOUR.2).

Files (all under `data/labels/`, human input except the sample):
* `validation_config.json` (owner): `{"neighborhoods": ["Roxbury", ...], "seed": 311, "n": 50}`; `seed` and `n` are optional.
* `validation_sample.csv` (written by `make validation-sample`, committed before any visit): the drawn zombies, never with
  the confidence score, so raters are blind to it.
* `validation_labels.csv` (two raters): `zombie_id, rater, label[, visited_on]`; labels `still broken`, `fixed since`,
  `different issue`, `can't tell` (spelling with spaces, underscores or a typographic apostrophe all read the same).

Scoring, per sampled zombie that has a label from two raters:
* `can't tell` from either rater: the zombie is a can't-tell case and is left out of precision.
* both `still broken`: confirmed. Any other rated pair counts as not confirmed (a disagreement is not a confirmation).
* precision = confirmed / rated (Wilson 95% interval); can't-tell share = can't-tell cases / zombies with two labels.
* Cohen's kappa over the four labels, plus the 2x2 version (still broken or not), both null when chance agreement is 1.
A missing label file means "awaiting field labels" and exit 0 (REQ-STAT-VAL.4).
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from undead311.stats.intervals import make_rate

SAMPLE_FILE = "validation_sample.csv"
LABELS_FILE = "validation_labels.csv"
CONFIG_FILE = "validation_config.json"
SAMPLE_SIZE = 50
RECENT_DAYS = 60
DEFAULT_SEED = 311
LABELS = ("still_broken", "fixed_since", "different_issue", "cant_tell")
SAMPLE_COLUMNS = ("zombie_id", "incident_id", "resurrection_id", "type_family", "neighborhood", "resurrection_date")
START = "<!-- field-validation:start -->"
END = "<!-- field-validation:end -->"


def norm_label(raw: str) -> str | None:
    """One of LABELS for a rater's text, or None when it is not a label."""
    s = re.sub(r"[^a-z]+", "_", raw.strip().lower().replace("’", "'").replace("'", "")).strip("_")
    return {"still_broken": "still_broken", "fixed_since": "fixed_since", "different_issue": "different_issue",
            "cant_tell": "cant_tell", "cannot_tell": "cant_tell"}.get(s)  # fmt: skip


def read_config(path: Path) -> dict | None:
    """The owner's config, or None when absent or without neighborhoods."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return None
    nbrs = data.get("neighborhoods") if isinstance(data, dict) else None
    if not isinstance(nbrs, list) or not nbrs or not all(isinstance(x, str) for x in nbrs):
        return None
    return {"neighborhoods": sorted(set(nbrs)), "seed": int(data.get("seed", DEFAULT_SEED)), "n": int(data.get("n", SAMPLE_SIZE))}


def draw_sample(zombies: list[dict], config: dict, snapshot_end: date) -> list[dict]:
    """The validation sample (REQ-STAT-VAL.1): headline zombies re-reported within RECENT_DAYS of `snapshot_end`, in the
    configured neighborhoods, drawn with a fixed seed from the ID-sorted candidates. Rows carry no confidence score."""
    since = (snapshot_end - timedelta(days=RECENT_DAYS)).isoformat()
    pool = sorted(
        (z for z in zombies
         if z.get("tier") == "headline" and z.get("neighborhood") in config["neighborhoods"]
         and since <= z.get("resurrection_date", "") <= snapshot_end.isoformat()),
        key=lambda z: z["zombie_id"],
    )  # fmt: skip
    rng = random.Random(config["seed"])
    picked = sorted(rng.sample(pool, min(config["n"], len(pool))), key=lambda z: z["zombie_id"])
    return [{c: z.get(c, "") for c in SAMPLE_COLUMNS} for z in picked]


def write_sample(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SAMPLE_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def read_sample_ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return sorted(r["zombie_id"] for r in csv.DictReader(f) if r.get("zombie_id"))


def read_labels(path: Path) -> dict[str, dict[str, str]]:
    """zombie_id -> {rater: label}; unreadable rows are skipped. The last row of a (zombie, rater) pair wins."""
    out: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return out
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            zid, rater, label = (r.get("zombie_id") or "").strip(), (r.get("rater") or "").strip(), norm_label(r.get("label") or "")
            if zid and rater and label:
                out.setdefault(zid, {})[rater] = label
    return out


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa of two raters' labels; None when it is undefined (no pairs, or chance agreement is 1)."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe >= 1.0:
        return None
    return max(-1.0, min(1.0, (po - pe) / (1 - pe)))


@dataclass(frozen=True)
class Validation:
    status: str
    sample_ids: tuple[str, ...]
    n_paired: int
    precision: dict | None
    cant_tell_share: float | None
    kappa: float | None
    kappa_still_broken: float | None
    confirmed: tuple[str, ...]

    def to_json(self, data_version: str) -> dict:
        return {
            "data_version": data_version, "status": self.status, "precision": self.precision,
            "cant_tell_share": self.cant_tell_share, "kappa": self.kappa, "kappa_still_broken": self.kappa_still_broken,
            "n_paired": self.n_paired, "confirmed": list(self.confirmed), "sample_ids": list(self.sample_ids),
        }  # fmt: skip


def score(sample_ids: list[str], labels: dict[str, dict[str, str]]) -> Validation:
    """Precision, can't-tell share, kappa and the confirmed set (REQ-STAT-VAL.2-4). No two-rater pair: awaiting labels."""
    pairs: list[tuple[str, tuple[str, str]]] = []
    for zid in sorted(labels):
        if sample_ids and zid not in sample_ids:
            continue
        raters = sorted(labels[zid])
        if len(raters) >= 2:
            pairs.append((zid, (labels[zid][raters[0]], labels[zid][raters[1]])))
    if not pairs:
        return Validation("awaiting_field_labels", tuple(sample_ids), 0, None, None, None, None, ())
    cant = [z for z, (x, y) in pairs if "cant_tell" in (x, y)]
    rated = [(z, p) for z, p in pairs if z not in set(cant)]
    confirmed = tuple(z for z, (x, y) in rated if x == y == "still_broken")
    a, b = [p[0] for _, p in pairs], [p[1] for _, p in pairs]
    two = lambda xs: ["still_broken" if x == "still_broken" else "other" for x in xs]
    return Validation(
        "scored", tuple(sample_ids), len(pairs), make_rate(len(confirmed), len(rated)).to_json(),
        len(cant) / len(pairs), cohen_kappa(a, b), cohen_kappa(two(a), two(b)), confirmed,
    )  # fmt: skip


def render_section(v: Validation) -> str:
    """The marked block written to docs/VALIDATION.md. It has no date, so a rerun gives the same bytes."""
    lines = [START, "## Field validation of possible zombies", ""]
    if v.status != "scored":
        lines += [f"Awaiting field labels: `data/labels/{LABELS_FILE}` has no zombie labeled by two raters.", END]
        return "\n".join(lines) + "\n"
    p = v.precision or {}
    pct = lambda x: "n/a" if x is None else f"{x:.1%}"
    kap = lambda x: "undefined" if x is None else f"{x:.2f}"
    lines += [
        f"{v.n_paired} sampled zombies were labeled by two raters.",
        "",
        "- Precision (both raters: still broken, of the zombies neither called can't tell): "
        + f"{pct(p.get('rate'))} ({p.get('k')} of {p.get('n')}), Wilson 95% interval {pct(p.get('lo'))} to {pct(p.get('hi'))}.",
        f"- Can't-tell share: {pct(v.cant_tell_share)}.",
        f"- Cohen's kappa, four labels: {kap(v.kappa)}; still broken or not: {kap(v.kappa_still_broken)}.",
        f"- Confirmed zombies (both raters: still broken): {len(v.confirmed)}.",
        END,
    ]
    return "\n".join(lines) + "\n"


def write_section(validation_md: Path, section: str) -> None:
    p = Path(validation_md)
    text = p.read_text(encoding="utf-8") if p.is_file() else "# Validation\n"
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
    new = pattern.sub(lambda _m: section, text) if pattern.search(text) else text.rstrip("\n") + "\n\n" + section
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8")


def run_validate(labels_dir: Path, validation_md: Path, out_json: Path | None, data_version: str = "unknown") -> tuple[int, str]:
    """`make validate`: score the labels, update docs/VALIDATION.md and (when `out_json` is given) validation.json."""
    v = score(read_sample_ids(labels_dir / SAMPLE_FILE), read_labels(labels_dir / LABELS_FILE))
    write_section(validation_md, render_section(v))
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(v.to_json(data_version), sort_keys=True, indent=1) + "\n")
    if v.status != "scored":
        return 0, "validate: awaiting field labels"
    p = v.precision or {}
    return 0, f"validate: precision {p.get('rate')} ({p.get('k')}/{p.get('n')}), kappa {v.kappa}, confirmed {len(v.confirmed)}"


def read_zombie_records(zombies_json: Path) -> list[dict] | None:
    """The zombie records of an export: one `zombies.json` (earlier runs) or the shards of `zombies/` beside it (REQ-EXP-SIZE.3),
    sorted by zombie_id as the one-piece file was. None when neither exists."""
    if zombies_json.is_file():
        return json.loads(zombies_json.read_text()).get("zombies", [])
    folder = zombies_json.with_name("zombies")
    if not folder.is_dir():
        return None
    rows = [z for f in sorted(folder.glob("*.json")) if f.name != "index.json" for z in json.loads(f.read_text())["zombies"]]
    return sorted(rows, key=lambda z: z["zombie_id"])


def run_validation_sample(labels_dir: Path, zombies_json: Path, snapshot_end: date) -> tuple[int, str]:
    """`make validation-sample`: draw and write `validation_sample.csv`. Missing owner config or zombies: message, exit 0."""
    config = read_config(labels_dir / CONFIG_FILE)
    if config is None:
        return 0, f"validation-sample: {labels_dir / CONFIG_FILE} is missing or lists no neighborhoods; the owner chooses them"
    records = read_zombie_records(zombies_json)
    if records is None:
        return 0, f"validation-sample: {zombies_json} (or its zombies/ shards) is missing; run the pipeline first"
    target = labels_dir / SAMPLE_FILE
    if target.is_file():
        return 0, f"validation-sample: {target} already exists and stays as committed (it is drawn once, before any visit)"
    rows = draw_sample(records, config, snapshot_end)
    write_sample(target, rows)
    return 0, f"validation-sample: wrote {len(rows)} zombies to {target}"
