"""Unit tests for undead311.ingest.times (REQ-ING-TZ)."""

from datetime import UTC, datetime

from undead311.ingest.times import parse_new_system_stamp, to_utc_and_local


def conv(s):
    return to_utc_and_local(datetime.fromisoformat(s))


def test_summer_and_winter_offsets():
    assert conv("2026-07-01 12:00:00")[0] == datetime(2026, 7, 1, 16, tzinfo=UTC)
    assert conv("2026-01-15 12:00:00")[0] == datetime(2026, 1, 15, 17, tzinfo=UTC)


def test_spring_forward_gap_shifted_and_flagged():
    utc, local, flags = conv("2026-03-08 02:30:00")
    assert flags == {"local_nonexistent"}
    assert local == datetime(2026, 3, 8, 3, 30)
    assert utc == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)


def test_fall_back_ambiguous_uses_first_occurrence():
    utc, local, flags = conv("2026-11-01 01:30:00")
    assert flags == {"local_ambiguous"}
    assert local == datetime(2026, 11, 1, 1, 30)
    assert utc == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # EDT


def test_plain_time_has_no_flags():
    assert conv("2026-11-01 02:30:00")[2] == frozenset()
    assert conv("2026-03-08 03:00:00")[2] == frozenset()


def test_plus_00_suffix_is_ignored():
    for s in ["2026-07-16 16:10:24.446642+00", "2026-07-17 08:06:36+00"]:
        assert parse_new_system_stamp(s) == datetime.fromisoformat(s[:-3])
    assert parse_new_system_stamp(None) is None
    assert parse_new_system_stamp("") is None


def test_new_and_legacy_same_wall_clock_give_same_utc():
    new = to_utc_and_local(parse_new_system_stamp("2026-07-16 16:10:24+00"))[0]
    legacy = conv("2026-07-16 16:10:24")[0]
    assert new == legacy == datetime(2026, 7, 16, 20, 10, 24, tzinfo=UTC)
