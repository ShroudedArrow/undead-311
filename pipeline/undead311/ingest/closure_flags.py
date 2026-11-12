"""Transfer-closure and cross-system mirror detection (REQ-ING-MIRROR).

A legacy case closed with "Resubmitted as BCS-..." was re-created in the new system at
migration; the pair (original, re-report) is a hand-off copy, not a zombie. Likewise a legacy and
a new case for the same family and place opened within a few hours of each other are mirrors.
The mirror rule is cross-system only: same-system pairs follow the normal rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

MIRROR_WINDOW_HOURS = 6

TRANSFER_CLOSURE_RE = re.compile(
    r"BCS-?\d+|resubmitted as|see new case|new case (has been created|number|entered|ref|#)"
    r"|a new case has been created|transferr?ed|migrat|transition(ed)? to",
    re.IGNORECASE,
)


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

    Rows need keys system, open_utc (aware datetime), type_family, closure_text, optional closure_code. Location equality is
    the caller's matching rule (default True: the pair was matched on location already).
    """
    if is_transferred_original(original):
        return False
    return not is_mirror_pair(
        original["system"],
        rereport["system"],
        original["open_utc"],
        rereport["open_utc"],
        original["type_family"] == rereport["type_family"],
        same_location,
    )
