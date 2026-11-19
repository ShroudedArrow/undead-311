"""Staff names written in the middle of a note (REQ-ING-PII.7).

The sign-off, slash-name and name-with-title patterns miss a name that stands alone inside a sentence:
"Firstname Lastname @ <place>" and "Firstname from <organization>". Three rules remove those, using a list of the 2,000
most common US first names (`first_names.txt`, SSA public data; source and build in `pipeline/scripts/build_first_names.py`):

(a) `first_name`: two adjacent capitalized words, the first on the list and the second not a street suffix, a street
    word, a known place or an ordinary note word ("Washington St", "Columbus Ave", "Franklin Park", "Case Closed").
    Both words are removed.
(b) `first_name_from`: a listed first name followed by "from" and a capitalized word ("Dana from National Grid"). The
    first name is removed; "from" and the organization stay.
(c) `name_at`: in "<name> @ <place>" the pair is removed on a weaker test (the second word may be a street word), because
    the "@" shows a person at a place. The place after the "@" always stays.

Two more forms (REQ-ING-PII.7): `first_name_beside_removed` (a listed first name directly beside `[removed]`, on either side,
only the first name goes) and `first_name_initial` ("Mike S." / "Mike S": the pair goes, the period stays unless a surname
follows it; kept before a street suffix, known place or street word, and for "X"). `scrub` runs these rules last, after the
patterns and the staff list, so they see every `[removed]`.

Street words come from the run (`set_place_words`: SAM segment names and the case street list), plus the static
`STREET_SUFFIXES` and `PLACES` here. A name that is also a street word is kept: a lost name is the cheaper mistake than
a street erased from a note. Replacement text is `[removed]`; the rules never see their own output, so they are idempotent.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

REMOVED = "[removed]"


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


MAX_PASSES = 5
NAMES_FILE = Path(__file__).with_name("first_names.txt")

STREET_SUFFIXES = _words(
    "st street ave avenue av rd road blvd boulevard way pl place sq square ter terrace terr ln lane dr drive ct court "
    "hwy highway pkwy parkway park cir circle bridge wharf pier path walk alley row plaza hill heights common garden "
    "gardens playground station tunnel center centre ctr fwy expy expressway pike turnpike landing green field fields "
    "yard yards pond river basin beach point cove island islands harbor harbour bay lot gate gateway mall market "
    "stadium arena rink pool school church hospital library bldg building tower towers crossing xing ramp loop trail "
    "greenway esplanade promenade extension ext connector lane lanes"
)
# Places that can follow a first name and are not streets in the SAM file: neighborhoods, towns, landmarks.
PLACES = _words(
    "allston brighton dorchester roxbury mattapan roslindale charlestown fenway kenmore longwood seaport chinatown "
    "downtown cambridge somerville brookline quincy newton milton revere chelsea medford malden everett watertown "
    "needham dedham boston massachusetts logan airport copley prudential faneuil quincy kennedy fiedler luther king "
    "jamaica savin franklin columbia andrew uphams dudley ruggles egleston forest hills jackson roslin lower upper "
    "north south east west central beacon bunker commonwealth huntington harvard tremont boylston newbury hanover "
    "milk federal summer winter spring autumn cummins morton blue washington lincoln jefferson madison adams hamilton monroe"
)
# Capitalized words that follow a name-like word in ordinary notes.
NOTE_WORDS = _words(
    "the a an and or of for to in on at by with from is was will be has have case noted resolved invalid duplicate "
    "closed open new old public works city department dept division highway lighting traffic transportation water sewer "
    "parks recreation management inspection unit engineering utility utilities maintenance operations construction "
    "services service commission office bureau contact call please thank thanks sincerely regards dear constituent "
    "resident residents customer sir madam mr mrs ms miss mx dr area light lights pole poles sign signs pothole "
    "potholes sidewalk sidewalks roadway street tree trees repair repairs repaired replace replaced removed remove "
    "install installed temporary permanent private owner owners property fixture fixtures signal signals marking "
    "markings crosswalk catch basin basins manhole cover covers wire wires cable cables lamp lamps electric gas "
    "national grid eversource verizon comcast bwsc btd pwd isd ons dpw mbta dcr mass crew crews staff team "
    # business words ("Cassidy Landscaping", "Riley Brothers"), titles, function words and verbs
    "landscaping landscape brothers bros group excavation excavating contracting contractor contractors company co inc "
    "llc corp corporation associates enterprises plumbing paving trucking towing realty properties development builders "
    "equipment supply systems solutions partners industries attachments sons son lines director directors engineer "
    "engineers supervisor supervisors foreman manager managers inspector inspectors commissioner chief assistant deputy "
    "this that these those it its as are were been being do did does not no yes if so but then than also only just "
    "sent help follow issue need see per via our your their his her he she we they you i me my us who what when where "
    "which how why all any each every some more most other another about after before again back down up out over under "
    "august april june july may march september october november december january february monday tuesday wednesday "
    "thursday friday saturday sunday "
    # ordinary words and Boston-area place names found after a first name in the full data (checked by hand)
    "location clear cart code streets there today can still swept one moved animal broken complete must week glass patch "
    "take police community plate like project food squirrel good boxes note companies furniture led store unfortunately "
    "health bench fully restaurant ends complex air roads bottles real family recall rule steam medical pizza convenience "
    "mgmt christmas apt generally college apartments stroller environment exception sts fri golf variety senior"
)

_AMBIGUOUS_FIRST = _words(
    "will may june april august summer dawn hope faith grant joy rose lane quincy milton everett chelsea newton lincoln washington franklin jefferson madison"
)  # ordinary words and Boston-area place names
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\u2019-]*")
_FIRST = re.compile(r"[A-Z][a-z]+")
_SECOND = re.compile(r"[A-Z](?:[a-z]+|['\u2019][A-Z][a-z]+)(?:['\u2019-]?[A-Z][a-z]+)?")
_GAP_SPACE = re.compile(r"\s+")
_GAP_AT = re.compile(r"\s*@")
_REMOVED_AFTER = re.compile(r"\s+\[removed\]")
_REMOVED_BEFORE = re.compile(r"\[removed\]\s+$")
_INITIAL = re.compile(r"[A-WYZ]")  # not X: "Malcolm X"
_DOTTED = re.compile(r"\.[A-Za-z]")  # "S.W.": a direction or an abbreviation, not one initial

_place_words: frozenset[str] = frozenset()


def set_place_words(words: Iterable[str]) -> int:
    """Street words of this run (lower-case) that a second word must not be. An empty iterable switches them off."""
    global _place_words
    _place_words = frozenset(w.lower() for w in words if w)
    return len(_place_words)


@lru_cache(maxsize=1)
def first_names() -> frozenset[str]:
    """The listed first names, lower-case."""
    lines = NAMES_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(ln.strip() for ln in lines if ln.strip() and not ln.startswith("#"))


def _second_ok(word: str, relaxed: bool) -> bool:
    w = word.lower()
    if not _SECOND.fullmatch(word) or w in STREET_SUFFIXES or w in NOTE_WORDS:
        return False
    if len(w) > 5 and w.endswith(("ed", "ing")):  # a verb ("Alexander Inspected"), not a surname
        return False
    # "<name> @ <place>": the "@" shows a person at a place, so a street word may be a surname.
    return relaxed or (w not in PLACES and w not in _place_words)


def _street_follows(text: str, toks: list[re.Match[str]], j: int, after: int) -> bool:
    """True when the word after an initial is a street suffix, a known place or a street word of the run: "William F McClellan
    Hwy", "Malcolm X Blvd", "Richard B. Ross Way" are street names with a middle initial, not a name and an initial."""
    if j >= len(toks) or not re.fullmatch(r"\.?\s+", text[after : toks[j].start()]):
        return False
    w = toks[j].group().lower()
    return w in STREET_SUFFIXES or w in PLACES or w in _place_words


def find(text: str) -> list[tuple[int, int, str, str]]:
    """Spans to replace as (start, end, rule, replacement), in text order, never overlapping."""
    toks = list(_TOKEN.finditer(text))
    names = first_names()
    out: list[tuple[int, int, str, str]] = []
    i = 0
    while i < len(toks):
        a = toks[i]
        b = toks[i + 1] if i + 1 < len(toks) else None
        if not (
            _FIRST.fullmatch(a.group())
            and a.group().lower() in names
            and a.group().lower() not in _AMBIGUOUS_FIRST
        ):
            i += 1
            continue
        if b is None:
            if _REMOVED_BEFORE.search(text, 0, a.start()):
                out.append((a.start(), a.end(), "first_name_beside_removed", REMOVED))
            break
        gap = text[a.end() : b.start()]
        if b.group() == "from" and _GAP_SPACE.fullmatch(gap) and i + 2 < len(toks):
            c = toks[i + 2]
            if _GAP_SPACE.fullmatch(text[b.end() : c.start()]) and re.match(r"[A-Z]", c.group()):
                out.append((a.start(), a.end(), "first_name_from", REMOVED))
                i += 2
                continue
        if (
            _GAP_SPACE.fullmatch(gap)
            and _INITIAL.fullmatch(b.group())
            and not _DOTTED.match(text, b.end())
            and not _street_follows(text, toks, i + 2, b.end())
        ):
            # "Mike S." or "Mike S": the first name and the initial. A period stays unless a surname follows it.
            end = b.end()
            if text.startswith(". ", end) and i + 2 < len(toks):
                c = toks[i + 2]
                if c.start() == end + 2 and _SECOND.fullmatch(c.group()) and _second_ok(c.group(), False):
                    end, i = c.end(), i + 1
            out.append((a.start(), end, "first_name_initial", REMOVED))
            i += 2
            continue
        if _GAP_SPACE.fullmatch(gap):
            at = _GAP_AT.match(text, b.end())
            relaxed = at is not None
            if _second_ok(b.group(), relaxed):
                out.append((a.start(), b.end(), "name_at" if relaxed else "first_name", REMOVED))
                i += 2
                continue
        if _REMOVED_AFTER.match(text, a.end()) or _REMOVED_BEFORE.search(text, 0, a.start()):
            out.append(
                (a.start(), a.end(), "first_name_beside_removed", REMOVED)
            )  # a name next to a removed surname
        i += 1
    return out


def apply(text: str) -> tuple[str, Counter[str]]:
    """`text` with the rules applied, and the replacement count per rule. A pass can leave a first name beside a `[removed]`
    that the same pass made ("Maggie Van Scoy" with "Van Scoy" removed), so passes repeat until nothing changes; each pass
    shortens the text or the count of names, so it stops (at most `MAX_PASSES`) and a second call changes nothing."""
    counts: Counter[str] = Counter()
    for _ in range(MAX_PASSES):
        spans = find(text)
        if not spans:
            break
        for start, end, rule, repl in reversed(spans):
            text = text[:start] + repl + text[end:]
            counts[rule] += 1
    return text, counts
