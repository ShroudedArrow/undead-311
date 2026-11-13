"""Personal-information scrubbing for free text (REQ-ING-PII).

Replaced with `[removed]`: email addresses, phone numbers, names after an honorific (Mr, Mrs, Ms, Miss, Mx, Dr) or
after "called by", "spoke with" and "per", and digit runs of 7 or more. Addresses and street names are public case
locations and are kept (REQ-ING-PII.2). Case IDs written `BCS-<digits>` are public identifiers and are kept.
Replacements are counted per pattern; the removed text is never logged or returned (REQ-ING-PII.3).
The scrub is idempotent: `[removed]` contains nothing any pattern matches.
"""

from __future__ import annotations

import re
from collections import Counter

REMOVED = "[removed]"

_NAME = r"[A-Z][a-z'\u2019-]+(?:\s+[A-Z][a-z'\u2019-]+){0,2}"

# (pattern name, regex, replacement). Order matters: contact details first, bare digit runs last.
PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), REMOVED),
    (
        "phone",
        re.compile(r"(?<![\w-])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)|(?<![\w-])\d{3}[-.]\d{4}(?!\d)"),
        REMOVED,
    ),
    ("honorific_name", re.compile(rf"\b((?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+)({_NAME})"), rf"\1{REMOVED}"),
    (
        "context_name",
        re.compile(rf"\b((?:[Cc]alled by|[Ss]poke with|[Pp]er)\s+)({_NAME})"),
        rf"\1{REMOVED}",
    ),
    ("digit_run", re.compile(r"(?<!BCS-)(?<!\d)\d{7,}"), REMOVED),
)


def scrub(text: str | None) -> tuple[str | None, Counter[str]]:
    """Return (scrubbed text, replacement counts per pattern). None stays None (REQ-ING-PII.1, .3)."""
    counts: Counter[str] = Counter()
    if text is None:
        return None, counts
    for name, regex, repl in PATTERNS:
        text, n = regex.subn(repl, text)
        if n:
            counts[name] += n
    return text, counts


def scrub_text(text: str | None) -> str | None:
    """Scrubbed text only."""
    return scrub(text)[0]


class PiiCounter:
    """Accumulates per-pattern counts over many fields for the run report (REQ-ING-PII.3)."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def scrub(self, text: str | None) -> str | None:
        out, c = scrub(text)
        self.counts.update(c)
        return out
