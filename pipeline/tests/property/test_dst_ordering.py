"""Property tests: DST-safe cross-system ordering (REQ-ING-TZ) and mirror filtering (REQ-DET-2.2)."""

from datetime import UTC, datetime, timedelta

from helpers import examples
from hypothesis import example, given, settings
from hypothesis import strategies as st

from undead311.ingest.closure_flags import MIRROR_WINDOW_HOURS, pair_survives
from undead311.ingest.times import BOSTON, parse_new_system_stamp, to_utc_and_local


def nth_sunday(year, month, n):
    d = datetime(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


@st.composite
def instants(draw):
    year = draw(st.integers(2015, 2027))
    if draw(st.booleans()):  # near a transition
        base = draw(st.sampled_from([nth_sunday(year, 3, 2), nth_sunday(year, 11, 1)]))
        off = draw(st.integers(-14 * 24 * 3600, 14 * 24 * 3600))
        return (base + timedelta(seconds=off)).replace(tzinfo=UTC)
    off = draw(st.integers(0, 365 * 24 * 3600 - 1))
    return (datetime(year, 1, 1) + timedelta(seconds=off)).replace(tzinfo=UTC)


def wall(utc_dt):
    return utc_dt.astimezone(BOSTON).replace(tzinfo=None)


def is_ambiguous(utc_dt):
    w = wall(utc_dt).replace(tzinfo=BOSTON)
    return w.replace(fold=0).utcoffset() != w.replace(fold=1).utcoffset()


def legacy_utc(utc_dt):
    return to_utc_and_local(wall(utc_dt))


def new_utc(utc_dt):
    return to_utc_and_local(parse_new_system_stamp(wall(utc_dt).strftime("%Y-%m-%d %H:%M:%S.%f") + "+00"))


@given(instants(), instants())
@example(datetime(2026, 11, 1, 4, 30, tzinfo=UTC), datetime(2026, 11, 1, 7, 30, tzinfo=UTC))
@settings(max_examples=examples(200), deadline=None)
def test_cross_system_ordering_matches_truth(a, b):
    if is_ambiguous(a) or is_ambiguous(b):
        return
    na, nb = legacy_utc(a)[0], new_utc(b)[0]
    assert (na < nb) == (a < b) and (na == nb) == (a == b)
    # durations equal true elapsed time
    assert (nb - na).total_seconds() == (b - a).total_seconds()


@given(instants())
@settings(max_examples=examples(200), deadline=None)
def test_ambiguous_hour_flagged_and_error_bounded(a):
    for conv in (legacy_utc, new_utc):
        got, _, flags = conv(a)
        if is_ambiguous(a):
            assert "local_ambiguous" in flags
            assert (got - a).total_seconds() in (0, -3600)
        else:
            assert "local_ambiguous" not in flags
            assert got == a


@given(instants())
@settings(max_examples=examples(200), deadline=None)
def test_roundtrip_identity_outside_ambiguous(a):
    if is_ambiguous(a):
        return
    got, local, _ = new_utc(a)
    assert local.replace(tzinfo=BOSTON).astimezone(UTC) == got == a.replace(microsecond=a.microsecond)


def test_naive_wallclock_comparison_is_wrong_across_fall_back():
    # 04:30 UTC (00:30 EDT) is earlier than 06:10 UTC (01:10 EST) ... but wall-clock digits say later
    a = datetime(2026, 11, 1, 5, 40, tzinfo=UTC)  # 01:40 EDT (first occurrence)
    b = datetime(2026, 11, 1, 6, 10, tzinfo=UTC)  # 01:10 EST (second occurrence)
    assert a < b and wall(a) > wall(b)  # naive wall-clock order is wrong
    assert is_ambiguous(a) and is_ambiguous(b)
    # a non-ambiguous pair spanning the transition is ordered correctly after normalization
    c, d = datetime(2026, 11, 1, 3, 59, tzinfo=UTC), datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    assert legacy_utc(c)[0] < new_utc(d)[0]


def test_treating_plus_00_as_utc_would_misorder():
    # a legacy case closed at 09:00 wall-clock and its new-system re-report at 09:02 wall-clock '+00'
    closed = to_utc_and_local(datetime(2026, 7, 1, 9, 0))[0]
    opened = to_utc_and_local(parse_new_system_stamp("2026-07-01 09:02:00+00"))[0]
    assert 0 < (opened - closed).total_seconds() < 600
    assert parse_new_system_stamp("2026-07-01 09:02:00+00").replace(tzinfo=UTC) < closed  # wrong reading


@given(
    gap_s=st.integers(-48 * 3600, 48 * 3600),
    transfer=st.booleans(),
    same_family=st.booleans(),
)
@settings(max_examples=examples(200), deadline=None)
def test_pair_survives_rule(gap_s, transfer, same_family):
    t0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
    orig = {
        "system": "legacy", "open_utc": t0, "type_family": "sign",
        "closure_text": "Resubmitted as BCS-00231479" if transfer else "Case Resolved",
    }  # fmt: skip
    rer = {"system": "new", "open_utc": t0 + timedelta(seconds=gap_s), "type_family": "sign" if same_family else "sidewalk"}
    got = pair_survives(orig, rer)
    if transfer or same_family and abs(gap_s) <= MIRROR_WINDOW_HOURS * 3600:
        assert not got
    else:
        assert got
