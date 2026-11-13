"""Property P20: the PII scrub is idempotent and removes every generated email and phone number (REQ-ING-PII.1)."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from undead311.ingest.pii import PATTERNS, REMOVED, scrub_text

words = st.text(alphabet=st.characters(whitelist_categories=("Ll",), max_codepoint=0x7A), min_size=1, max_size=8)
emails = st.builds(
    lambda u, d, t: f"{u}@{d}.{t}",
    st.text("abcdefghijklmnopqrstuvwxyz0123456789._", min_size=1, max_size=10).filter(lambda s: s[0] not in "._"),
    st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
    st.sampled_from(["com", "org", "net", "gov"]),
)
digits = st.text("0123456789", min_size=10, max_size=10)
phones = st.builds(
    lambda d, style: {
        0: f"({d[:3]}) {d[3:6]}-{d[6:]}",
        1: f"{d[:3]}-{d[3:6]}-{d[6:]}",
        2: f"{d[:3]}.{d[3:6]}.{d[6:]}",
        3: d,
        4: f"+1 {d[:3]} {d[3:6]} {d[6:]}",
    }[style],
    digits,
    st.integers(0, 4),
)
filler = st.lists(words, min_size=0, max_size=4).map(" ".join)


@given(filler, emails, filler, phones, filler)
def test_prop_p20_scrub_removes_generated_emails_and_phones(a, email, b, phone, c):
    """REQ-ING-PII.1: no generated email or phone number survives, and the scrub is idempotent."""
    text = f"{a} {email} {b} {phone} {c}"
    once = scrub_text(text)
    assert email not in once
    assert phone not in once
    assert not re.search(r"\d{7,}", once)
    assert scrub_text(once) == once
    assert once.count(REMOVED) >= 2


@given(st.text(max_size=60))
def test_prop_p20_scrub_is_idempotent_on_arbitrary_text(text):
    """REQ-ING-PII.1: scrubbing twice equals scrubbing once, for any text; only [removed] markers are introduced."""
    once = scrub_text(text)
    assert scrub_text(once) == once
    assert all(regex.search(REMOVED) is None for _, regex, _ in PATTERNS)
