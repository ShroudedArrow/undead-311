"""Transfer-closure and cross-system mirror detection (REQ-ING-MIRROR).

A legacy case closed with "Resubmitted as BCS-..." was re-created in the new system at
migration; the pair (original, re-report) is a hand-off copy, not a zombie. Likewise a legacy and
a new case for the same family and place opened within a few hours of each other are mirrors.
The mirror rule is cross-system only: same-system pairs follow the normal rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

MIRROR_WINDOW_HOURS = 6

TRANSFER_CLOSURE_RE = re.compile(
    r"BCS-?\d+|resubmitted as|see new case|new case (has been created|number|entered|ref|#)"
    r"|a new case has been created|transferr?ed|migrat|transition(ed)? to",
    re.IGNORECASE,
)

LINKED_CASE_RE = re.compile(r"BCS-(\d+)", re.IGNORECASE)

NEW_SYSTEM_CLOSURE_LABELS = {
    "Resolved": "resolved",
    "Resolved successfully": "resolved",
    "Noted": "noted",
    "Transitioned": "referred",
}


def new_system_closure_label(code: str | None) -> str | None:
    return NEW_SYSTEM_CLOSURE_LABELS.get(code) if code else None


def is_transfer_closure(text: str | None) -> bool:
    return bool(text) and TRANSFER_CLOSURE_RE.search(text) is not None


def extract_linked_case_id(text: str | None) -> str | None:
    """First 'BCS-<digits>' in a legacy transfer closure text, upper-cased; None if not a transfer closure."""
    if not is_transfer_closure(text):
        return None
    m = LINKED_CASE_RE.search(text)
    return f"BCS-{m.group(1)}" if m else None


def resolve_catch_all(
    default_family: str,
    predecessors: Sequence[tuple[str, str]],
    families: Mapping[str, tuple[str, str]],
) -> tuple[str, str, list[str]]:
    """Family and tier for a catch-all new-system case (REQ-ING-MIRROR).

    predecessors: (legacy case id, legacy type_raw) for each legacy case whose closure text links here.
    families: legacy type_raw -> (type_family, scope_tier). If every predecessor type is listed and all agree,
    the case inherits that family and tier. Otherwise (no link, unlisted type, disagreement) it stays
    sensitivity-only with the catch-all's default family. Returns (type_family, scope_tier, predecessor_ids).
    """
    ids = sorted(pid for pid, _ in predecessors)
    outcomes = {families.get(t) for _, t in predecessors}
    if predecessors and None not in outcomes and len(outcomes) == 1:
        family, tier = next(iter(outcomes))
        return family, tier, ids
    return default_family, "sensitivity", ids


def is_transferred_original(row: Mapping[str, Any]) -> bool:
    """True if the row was handed off: legacy transfer closure text, or new-system code 'Transitioned'.

    Row keys: system, closure_text, closure_code (optional). 'Noted' is still a valid original.
    """
    if row["system"] == "legacy":
        return is_transfer_closure(row.get("closure_text"))
    return row["system"] == "new" and new_system_closure_label(row.get("closure_code")) == "referred"


def is_mirror_pair(
    a_system: str,
    b_system: str,
    a_open_utc: datetime,
    b_open_utc: datetime,
    same_family: bool,
    same_location: bool,
) -> bool:
    """Cross-system only: same-system pairs follow the normal rules and are never mirrors."""
    if a_system == b_system or not (same_family and same_location):
        return False
    return abs((a_open_utc - b_open_utc).total_seconds()) <= MIRROR_WINDOW_HOURS * 3600


def pair_survives(original: Mapping[str, Any], rereport: Mapping[str, Any], same_location: bool = True) -> bool:
    """True if (original, rereport) is a real candidate pair.

    Rows need keys system, open_utc (aware datetime), type_family, closure_text, optional closure_code, id, predecessor_ids. Location equality is
    the caller's matching rule (default True: the pair was matched on location already).
    """
    if is_transferred_original(original):
        return False
    # a linked catch-all case continues its legacy predecessor; it is never a re-report of it
    if original.get("id") is not None and original["id"] in (rereport.get("predecessor_ids") or ()):
        return False
    return not is_mirror_pair(
        original["system"],
        rereport["system"],
        original["open_utc"],
        rereport["open_utc"],
        original["type_family"] == rereport["type_family"],
        same_location,
    )
