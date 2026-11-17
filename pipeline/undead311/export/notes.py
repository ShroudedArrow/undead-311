"""Which closure notes the site may show (REQ-ING-PII.5).

A closure note is free text typed by city staff, and it can carry a name that no pattern recognizes. The site shows a note
only when its scrubbed text appears in at least `MIN_NOTE_CASES` closed cases, counting texts that differ only in dates,
times and numbers as the same text (the masked template of `undead311.coroner.templates`). A note that fewer cases share
is not shown; the card says "free-text note not shown". The rule uses the scrubbed text, so two notes that differ only in
a name the scrub removed count as one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from undead311.coroner.templates import mask_template
from undead311.ingest.pii import scrub_text

MIN_NOTE_CASES = 5


def note_key(text: str | None) -> str:
    """The masked, scrubbed text that notes are counted by."""
    return mask_template(scrub_text(text))


def note_counts(texts: Iterable[str | None]) -> Counter[str]:
    """Closed cases per note key; empty and missing texts are not counted."""
    counts: Counter[str] = Counter()
    for text in texts:
        key = note_key(text) if text else ""
        if key:
            counts[key] += 1
    return counts


def shown_note(text: str | None, counts: Counter[str] | dict[str, int], minimum: int = MIN_NOTE_CASES) -> tuple[str | None, bool]:
    """(text to show, hidden). A note shared by fewer than `minimum` cases is hidden: (None, True). No text: (None, False)."""
    if not text:
        return None, False
    scrubbed = scrub_text(text)
    key = mask_template(scrubbed)
    if not key:
        return scrubbed, False
    if counts.get(key, 0) >= minimum:
        return scrubbed, False
    return None, True
