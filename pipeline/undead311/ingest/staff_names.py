"""The run-time staff-name list (REQ-ING-PII.6).

Closure notes carry staff names that appear outside the shapes the scrub patterns know ("Webb  Lynch." with no slash,
"V Mejias B Santry"). The names that the sign-off, slash-name and name-with-title patterns remove are collected from the
data itself (surnames, and the surname of an X.SURNAME form). A token is dropped from the list when it is also a street
word (the SAM segments or the case street list), is a common work or title word, or was removed from fewer than
`MIN_CASES` cases. The list is then removed wherever it appears as a standalone token in a note.

The list is built on every full run, from the run's own data, and written to `$DATA_DIR/staff_names.txt`. It is never
committed: nothing in the repository holds a staff name, only this code and the count the run reports. A sample run reads
the file when it exists and runs without the list when it does not.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from undead311.ingest import pii

MIN_CASES = 3
MIN_LENGTH = 3
OUTSIDE_RATIO = 25  # a token seen as a plain word in more than 25 times as many cases as it was removed from is a word, not a name
FILE_NAME = "staff_names.txt"
_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019-]*")
_WORD_LOWER = re.compile(r"[a-z][a-z'\u2019-]*")
_CAP_WORD = re.compile(r"[A-Z][A-Za-z'\u2019-]{2,}")
_NOT_NAMES = {w.lower() for w in (pii._CAP_STOP + "|" + pii._BARE_STOP).split("|")} | {"mc", "mac", "removed"}


def _surname_of_initial_form(token: str) -> str | None:
    """"A.LOWELL" -> "lowell"; the caller splits a run into its parts."""
    m = re.fullmatch(r"(?:[A-Za-z]\.)+\s?(?:Mc\s?|Mac\s?)?([A-Za-z'\u2019-]{2,})", token.strip(), re.IGNORECASE)
    return m.group(1).lower() if m else None


def harvest_text(text: str) -> set[str]:
    """Candidate names this text gives: what the three staff-name patterns would remove, as lower-case surname tokens."""
    out: set[str] = set()
    for rx in (pii._SLASH_INITIALS, pii._SPACED_INITIALS, pii._SLASH_BARE):
        for m in rx.finditer(text):
            for part in re.split(r"\s*/\s*|[\s,&]{2,}|(?<=[A-Za-z])\s+(?=[A-Za-z]\.[A-Za-z])", m.group()):
                sur = _surname_of_initial_form(part)
                if sur:
                    out.add(sur)
                elif _WORD.fullmatch(part.strip()):
                    out.add(part.strip().lower())
    for m in pii._NAME_BEFORE_TITLE.finditer(text):
        words = _CAP_WORD.findall(m.group())
        if words:
            out.add(words[-1].lower())
    for m in pii._NAME_AFTER_TITLE.finditer(text):
        words = _CAP_WORD.findall(m.group()[len(m.group(1)):])
        if words:
            out.add(words[-1].lower())
    for m in pii._SIGNOFF_SCRUB.finditer(text):
        run: list[str] = []
        for w in _CAP_WORD.finditer(text[m.end(): m.end() + 80]):
            if w.group().lower() in _NOT_NAMES:
                break
            run.append(w.group().lower())
            if len(run) == 3:
                break
        if len(run) >= 2:
            out.add(run[-1])
    return {t for t in out if len(t) >= MIN_LENGTH and t not in _NOT_NAMES}


def street_words(streets: Iterable[str | None], sam_geojson: Path | None = None) -> set[str]:
    """Lower-case words of the case street list and, when the file exists, of the SAM segment street names."""
    words: set[str] = set()
    for s in streets:
        if s:
            words.update(w.lower() for w in _WORD.findall(s))
    if sam_geojson is not None and Path(sam_geojson).is_file():
        for f in json.loads(Path(sam_geojson).read_text()).get("features", []):
            props = f.get("properties") or {}
            for key in ("ST_NAME", "ALTERNATE_NAME"):
                if props.get(key):
                    words.update(w.lower() for w in _WORD.findall(str(props[key])))
    return words


def build(texts: Iterable[tuple[str | None, int]], streets: set[str], min_cases: int = MIN_CASES) -> set[str]:
    """The names: harvested from `(text, n_cases)` pairs, removed from fewer than `min_cases` cases or matching a street word
    dropped (REQ-ING-PII.6). A token that also occurs as an ordinary word in more than `OUTSIDE_RATIO` times as many cases as it
    was harvested from is dropped too ("location", "have", "grid")."""
    seen: Counter[str] = Counter()
    words: Counter[str] = Counter()
    for text, n in texts:
        if text:
            for name in harvest_text(text):
                seen[name] += n
            for w in set(_WORD_LOWER.findall(text.lower())):
                words[w] += n
    return {n for n, c in seen.items() if c >= min_cases and n not in streets and words[n] - c <= OUTSIDE_RATIO * c}


def names_path(data_dir: Path) -> Path:
    return Path(data_dir) / FILE_NAME


def write_names(path: Path, names: Iterable[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(sorted(names)) + "\n", encoding="utf-8")


def read_names(path: Path) -> set[str]:
    p = Path(path)
    return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()} if p.is_file() else set()


def build_from_raw(min_cases: int | None = None) -> str:
    """`python -m undead311 staff-names`: build the list from `$DATA_DIR/raw`, write it to `$DATA_DIR/staff_names.txt` and
    return one line with the count. Runs load, normalize, crosswalk and clean in memory (about 2 minutes on the full data)."""
    from undead311.duck import connect
    from undead311.ingest.clean import clean
    from undead311.ingest.crosswalk import apply_crosswalk
    from undead311.ingest.load import load
    from undead311.ingest.normalize import normalize
    from undead311.ingest.snap import SEGMENTS_FILE
    from undead311.ingest.text import register_text_udfs
    from undead311.paths import data_dir, worktree_root

    base = data_dir()
    con = connect()
    register_text_udfs(con)
    load(con, base / "raw", worktree_root() / "data" / "SNAPSHOT.md")
    normalize(con)
    apply_crosswalk(con)
    clean(con)
    texts = con.execute("select closure_text, count(*) from cases_clean where closure_text is not null group by 1").fetchall()
    streets = street_words((r[0] for r in con.execute("select distinct street from cases_clean").fetchall()), base / "raw" / SEGMENTS_FILE)
    names = build(texts, streets, MIN_CASES if min_cases is None else min_cases)
    write_names(names_path(base), names)
    return f"staff names: {len(names)} (written to {names_path(base)}; never committed)"
