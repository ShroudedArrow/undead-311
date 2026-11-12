"""Time normalization for both 311 systems (REQ-ING-TZ).

Finding (2026-11-12 snapshot): the new-system ``open_date`` / ``close_date`` strings end in ``+00``
(87,951 of 87,951 rows) but are NOT UTC. They are Boston wall-clock time with a misleading suffix.
Evidence: for 1,373 legacy cases closed with "Resubmitted as / See new case BCS-N", the successor's
naive ``open_date`` minus the legacy naive ``closed_dt`` has median -2.6 minutes in every month from
Aug 2025 to Nov 2026, in DST and non-DST alike (real UTC would give 4 h or 5 h), and the hour-of-day
histogram of new-system opens peaks at 8-9 like legacy.

So BOTH systems are America/New_York wall-clock. We take the naive digits, ignore ``+00``,
interpret them as America/New_York, convert to UTC, and keep the wall-clock as the local value.

DST edges (wall-clock input):
* Fall-back hour (01:00-01:59 on the first Sunday of November) happens twice. We use fold=0
  (first occurrence, EDT) and set the flag ``local_ambiguous``. The UTC error is 0 or 3600 s.
* Spring-forward gap (02:00-02:59 on the second Sunday of March) never happens. The time is
  shifted forward (zoneinfo fold=0 behavior) and flagged ``local_nonexistent``; the returned local
  value is the shifted wall-clock.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BOSTON = ZoneInfo("America/New_York")
LOCAL_AMBIGUOUS = "local_ambiguous"
LOCAL_NONEXISTENT = "local_nonexistent"

_SUFFIX = re.compile(r"\s*(?:Z|[+-]\d{2}(?::?\d{2})?)$")


def parse_new_system_stamp(text: str | None) -> datetime | None:
    """Parse a new-system stamp like '2026-07-16 16:10:24.446642+00' as NAIVE wall-clock.

    The '+00' suffix is ignored on purpose (see module docstring).
    """
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    s = _SUFFIX.sub("", s).replace("T", " ")
    return datetime.fromisoformat(s)


def parse_legacy_stamp(text: str | None) -> datetime | None:
    """Parse a legacy stamp like '2015-01-02 08:13:00' as naive wall-clock."""
    if text is None:
        return None
    s = text.strip()
    return datetime.fromisoformat(s.replace("T", " ")) if s else None


def to_utc_and_local(wall_clock: datetime) -> tuple[datetime, datetime, frozenset[str]]:
    """Return (utc_aware, local_naive, flags) for a naive Boston wall-clock time."""
    if wall_clock.tzinfo is not None:
        raise ValueError("wall_clock must be naive")
    first = wall_clock.replace(tzinfo=BOSTON, fold=0)
    second = wall_clock.replace(tzinfo=BOSTON, fold=1)
    flags: set[str] = set()
    utc = first.astimezone(UTC)
    local = utc.astimezone(BOSTON).replace(tzinfo=None)
    if first.utcoffset() != second.utcoffset():
        flags.add(LOCAL_AMBIGUOUS if local == wall_clock else LOCAL_NONEXISTENT)
    return utc, local, frozenset(flags)
