"""Personal-information scrubbing for free text (REQ-ING-PII).

Replaced with `[removed]`: email addresses, phone numbers, names after an honorific (Mr, Mrs, Ms, Miss, Mx, Dr) or
after "called by", "spoke with" and "per", and digit runs of 7 or more. Staff names in closure notes (REQ-ING-PII.4):
everything after a sign-off phrase (`signoff`: "please do not hesitate to contact me", "Sincerely", "Regards",
"Thank you" followed by a name), runs of slash-separated surnames or initials (`slash_names`: "A.LOWELL / B.NASH",
and bare names such as "rowan/marsh" when they close the note), and the name beside a job title (`name_title`:
engineer, foreman, supervisor, manager, director, commissioner, inspector, chief). Names inside a sentence (REQ-ING-PII.7, `first_names.py`): "<first name> <word>", "<first name> from <organization>" and
"<name> @ <place>", using the 2,000 most common US first names; streets and known places are kept. Addresses and street names are public case
locations and are kept (REQ-ING-PII.2). Case IDs are public identifiers and are kept: new-system IDs written
`BCS-<digits>` in any letter case (`bcs-` too), and legacy IDs, which are exactly 12 digits starting with 101 (for example 101002227052; every legacy
`case_enquiry_id` has this form, ops#221). A longer digit run that starts with 101 is still removed.
Replacements are counted per pattern; the removed text is never logged or returned (REQ-ING-PII.3).
The scrub is idempotent: `[removed]` contains nothing any pattern matches.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from undead311.ingest import first_names

REMOVED = "[removed]"
LEGACY_CASE_ID = r"101\d{9}"  # legacy case_enquiry_id: 12 digits starting with 101 (ops#221)

_NAME = r"[A-Z][a-z'\u2019-]+(?:\s+[A-Z][a-z'\u2019-]+){0,2}"

# --- Staff names (REQ-ING-PII.4) -------------------------------------------------------------------------------------
_APOS = "'\u2019-"
# A word that follows "Thank you" without being a person's name ("Thank you for", "Thank you Boston 311").
_NOT_A_NAME = (
    "for|boston|city|your|you|the|in|so|very|again|and|to|we|from|public|constituent|resident|residents|customer|sir|"
    "madam|bos|btd|pwd|bwsc|dear|everyone|all|us|this|that|it|our|a|an|311|much|are|is|was|will|have|has|if|please|but|as|"
    "on|at|of|with|by|or|i|my"
)
# "I sincerely apologize", "we sincerely hope" and "with regards to" are sentences, not sign-offs.
_NOT_SIGNOFF = r"(?![\s,]+(?:apolog|regret|hope|thank|appreciate|believe|wish|understand|truly|want|mean)|\s+to\b|\s+and\b)"
SIGNOFF_PHRASES = (
    r"please\s+do\s+not\s+hesitate\s+to\s+(?:contact|call|e-?mail|reach)\b"
    r"|if\s+you\s+have\s+any\s+(?:(?:further|other|additional)\s+)?(?:questions|concerns)\b"
    r"|for\s+any\s+questions\s+or\s+concerns\b"
    rf"|\b(?:sincerely|respectfully|yours\s+truly|(?:(?:best|kind|warm)\s+)?regards)\b{_NOT_SIGNOFF}"
)
# "Thank you <name>" ends the note: at most ~100 characters (a title, a phone number) may follow the name.
_THANKS_TAIL = r"(?=.{0,100}$)"
_SIGNOFF_THANKS = rf"\bthank(?:s|\s+you)\b[,.!]*\s+(?!(?:{_NOT_A_NAME})\b)[a-z][a-z{_APOS}]+{_THANKS_TAIL}"
# Case-insensitive sign-off start. The "Thank you <name>" form needs a capital letter on the name here, so ordinary
# sentences in lower case are kept; `SIGNOFF_LOWER` (below) is the lower-case form used to match the masked templates.
_SIGNOFF_SCRUB = re.compile(
    rf"(?i:{SIGNOFF_PHRASES})|(?i:\bthank(?:s|\s+you))[,.!]*\s+(?!(?i:{_NOT_A_NAME})\b)[A-Z][A-Za-z{_APOS}]+{_THANKS_TAIL}",
    re.DOTALL,
)
SIGNOFF_LOWER = re.compile(rf"{SIGNOFF_PHRASES}|{_SIGNOFF_THANKS}", re.DOTALL)
_SIGNOFF_SCRUB_FULL = re.compile(rf"(?:{_SIGNOFF_SCRUB.pattern}).*", re.DOTALL)


def strip_signoff(text: str) -> str:
    """The lower-case text up to its first sign-off phrase: signatures and sign-off text cannot trigger Coroner cues."""
    m = SIGNOFF_LOWER.search(text)
    return text[: m.start()].rstrip() if m else text


# Slash-separated crew names: "A.LOWELL / B.NASH", "A.Mc DONALD /B.LOWELL", "rowan/marsh".
_INIT = rf"(?:[A-Za-z]\.\s?){{1,2}}(?:Mc|Mac)?\s?[A-Za-z][A-Za-z{_APOS}]+"
_BARE_STOP = (
    "and|the|utility|utilities|contractor|contractors|owner|owners|manager|managers|developer|developers|property|"
    "business|businesses|abutter|abutters|abbutters|resubmit|repair|repairs|repaired|replace|replaced|replacement|"
    "inspection|inspections|cleaned|sidewalk|sidewalks|roadway|pole|poles|sign|signs|fixture|fixtures|burner|lighting|"
    "pwd|ciu|btd|bwsc|homeowner|homeowners|outages|noted|expired|temporary|permanent|new|old|light|lights|street|tree|"
    "branch|water|sewer|gas|electric|private|public|city|state|pothole|potholes|patch|install|installed|removed|remove|"
    "cover|covers|cable|cables|wire|wires|feed|lamp|lamps|pit|and|not|any|all|for|with|case|closed|resolved|duplicate"
)
_BARE = rf"(?!(?:{_BARE_STOP})\b)[A-Za-z][A-Za-z{_APOS}]{{2,}}"
_TOKEN = rf"(?:{_INIT}|[A-Za-z][A-Za-z{_APOS}]{{2,}}|\.[A-Za-z]{{3,}}|\[removed\])"  # ".THOMPSON": a typo; "[removed]": cut by an earlier pattern
_SLASH_START = r"(?<![\w./:@-])"
_INITIAL_SURNAME = rf"[A-Za-z]\.(?:Mc\s?|Mac\s?)?[A-Za-z{_APOS}]{{3,}}"
_SLASH_END = r"(?![\w@-])(?!\.\w)"
# Only a date or a few initials may follow a bare-name run: staff sign the end of the note.
_NOTE_END = (
    r"(?=[\s.,;:-]*(?:(?:\d{1,2}[-/.]\d{1,2}(?:[-/.]\d{2,4})?(?!\d)|\[removed\]|[A-Za-z]{1,3}\.?(?![A-Za-z]))[\s.,;:-]*){0,4}$)"
)
_SLASH_INITIALS = re.compile(
    rf"{_SLASH_START}(?:(?:{_TOKEN})\s*/\s*)+{_INIT}(?:\s*/\s*{_TOKEN})*{_SLASH_END}"
    rf"|{_SLASH_START}{_INIT}(?:\s*/\s*{_TOKEN})+{_SLASH_END}",
    re.IGNORECASE,
)
_SPACED_INITIALS = re.compile(  # "M.DOYLE  D.WEBB": two or more initial-and-surname tokens in a row, no slash
    rf"{_SLASH_START}(?:{_INITIAL_SURNAME})(?:[\s,&]+{_INITIAL_SURNAME})+{_SLASH_END}", re.IGNORECASE
)
_SLASH_BARE = re.compile(rf"{_SLASH_START}{_BARE}(?:\s*/\s*{_BARE})+{_SLASH_END}{_NOTE_END}", re.IGNORECASE)

# Name beside a job title: "Michael Somers Senior Civil Engineer", "Chief Engineer Katie Choe".
_TITLES = r"(?:Engineer|Foreman|Supervisor|Manager|Director|Commissioner|Inspector|Chief)"
_QUALIFIERS = r"(?:(?:Senior|Chief|Assistant|Deputy|Civil|Principal|Acting|Associate|Project|Field|General|Area)\s+)*"
_CAP_STOP = (
    "The|A|An|Our|Your|This|That|Dear|Case|Noted|Resolved|Invalid|Duplicate|Closed|Boston|Public|Works|City|Department|"
    "Dept|Division|Highway|Street|Lighting|Traffic|Transportation|Water|Sewer|Parks|Recreation|Management|Inspection|"
    "Unit|Engineering|Utility|Utilities|Coordination|Maintenance|Operations|Construction|Services|Service|Commission|"
    "Office|Bureau|Of|For|And|With|Senior|Chief|Assistant|Deputy|Civil|Principal|Acting|Associate|Project|Field|General|"
    "Area|Engineer|Foreman|Supervisor|Manager|Director|Commissioner|Inspector|Thank|Thanks|Please|Contact|Call|Sincerely|"
    "Regards|If|It|We|He|She|They|Constituent|Hello|Hi|Good|Mr|Mrs|Ms|Miss|Mx|Dr|Sir|Madam|Resident|Residents"
)
_CAPNAME = rf"(?!(?:{_CAP_STOP})\b)[A-Z][a-z{_APOS}]+(?:[A-Z][a-z{_APOS}]+)?"
_NAME_BEFORE_TITLE = re.compile(
    rf"\b{_CAPNAME}(?:\s+(?:[A-Z]\.\s+)?{_CAPNAME}){{1,2}}\s+(?={_QUALIFIERS}{_TITLES}\b)"
)
_NAME_AFTER_TITLE = re.compile(rf"\b({_QUALIFIERS}{_TITLES})\s+{_CAPNAME}(?:\s+(?:[A-Z]\.\s+)?{_CAPNAME})?(?![\w'])")

# (pattern name, regex, replacement). Order matters: contact details first, bare digit runs last.
PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), REMOVED),
    (
        "phone",
        re.compile(r"(?<![\w-])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)|(?<![\w-])\d{3}[-.]\d{4}(?!\d)"),
        REMOVED,
    ),
    # REQ-ING-PII.4: staff names. The sign-off tail goes first, so the later patterns see only what is left.
    ("signoff", _SIGNOFF_SCRUB_FULL, REMOVED),
    ("slash_names", _SLASH_INITIALS, REMOVED),
    ("slash_names", _SLASH_BARE, REMOVED),
    ("slash_names", _SPACED_INITIALS, REMOVED),
    ("name_title", _NAME_BEFORE_TITLE, f"{REMOVED} "),
    ("name_title", _NAME_AFTER_TITLE, rf"\1 {REMOVED}"),
    ("honorific_name", re.compile(rf"\b((?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+)({_NAME})"), rf"\1{REMOVED}"),
    (
        "context_name",
        re.compile(rf"\b((?:[Cc]alled by|[Ss]poke with|[Pp]er)\s+)({_NAME})"),
        rf"\1{REMOVED}",
    ),
    # ops#221: a legacy case ID (12 digits starting with 101, not part of a longer run) is kept, like BCS- IDs.
    ("digit_run", re.compile(r"(?<![Bb][Cc][Ss]-)(?<!\d)(?!" + LEGACY_CASE_ID + r"(?!\d))\d{7,}"), REMOVED),
)


# --- Run-time staff-name list (REQ-ING-PII.6) -------------------------------------------------------------------------
# The list is built from the data by `undead311.ingest.staff_names` and lives only under DATA_DIR; no name is in the code.
_STAFF: re.Pattern[str] | None = None
_STAFF_COUNT = 0


def set_staff_names(names: Iterable[str]) -> int:
    """Use `names` (lower-case tokens) as standalone tokens to remove everywhere `scrub` runs with `staff=True`. An empty
    iterable switches the list off. Returns the number of names."""
    global _STAFF, _STAFF_COUNT
    ordered = sorted({n.lower() for n in names if n}, key=lambda n: (-len(n), n))
    _STAFF_COUNT = len(ordered)
    _STAFF = (
        re.compile(rf"(?<![\w{_APOS}])(?:{'|'.join(re.escape(n) for n in ordered)})(?![\w{_APOS}])", re.IGNORECASE)
        if ordered
        else None
    )
    return _STAFF_COUNT


def staff_name_count() -> int:
    """How many names the active list holds (the names themselves are never exposed)."""
    return _STAFF_COUNT


def scrub(text: str | None, staff: bool = True) -> tuple[str | None, Counter[str]]:
    """Return (scrubbed text, replacement counts per pattern). None stays None (REQ-ING-PII.1, .3). `staff=False` leaves
    out the run-time staff-name list."""
    counts: Counter[str] = Counter()
    if text is None:
        return None, counts
    for name, regex, repl in PATTERNS:
        text, n = regex.subn(repl, text)
        if n:
            counts[name] += n
    if staff and _STAFF is not None:
        text, n = _STAFF.subn(REMOVED, text)
        if n:
            counts["staff_name"] += n
    # REQ-ING-PII.7: last, so it sees every `[removed]` the patterns and the staff list left and can take a first name beside one
    text, first = first_names.apply(text)
    counts.update(first)
    return text, counts


def scrub_text(text: str | None, staff: bool = True) -> str | None:
    """Scrubbed text only."""
    return scrub(text, staff)[0]


class PiiCounter:
    """Accumulates per-pattern counts over many fields for the run report (REQ-ING-PII.3)."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def scrub(self, text: str | None) -> str | None:
        out, c = scrub(text)
        self.counts.update(c)
        return out
