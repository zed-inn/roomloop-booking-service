from datetime import date, datetime

import pytest

from roomloop.shared.utils.time import (
    TimeValidationError,
    format_naive_iso,
    generate_weekly_occurrences,
    parse_naive_iso,
    validate_local_wall_time,
)


def test_parse_and_format_naive_iso():
    """verifies parsing and formatting of canonical naive iso strings"""
    raw_str = "2026-10-21T09:00:00"
    parsed = parse_naive_iso(raw_str)
    assert parsed.year == 2026
    assert parsed.month == 10
    assert parsed.day == 21
    assert parsed.hour == 9
    assert parsed.minute == 0
    assert parsed.second == 0
    assert parsed.tzinfo is None

    formatted = format_naive_iso(parsed)
    assert formatted == raw_str


def test_parse_naive_iso_rejects_malformed_formats():
    """verifies that invalid timestamps or timestamps with offsets/microseconds are rejected"""
    invalid_samples = [
        "2026-10-21",
        "2026-10-21 09:00:00",
        "2026-10-21T09:00",
        "2026-10-21T09:00:00.000Z",
        "2026-10-21T09:00:00+02:00",
        "invalid-date",
        "",
    ]
    for sample in invalid_samples:
        with pytest.raises(TimeValidationError):
            parse_naive_iso(sample)


def test_validate_local_wall_time_catches_spring_forward_gap():
    """verifies that non-existent local wall times in spring-forward dst gaps are rejected"""
    gap_time = datetime(2027, 3, 28, 2, 30, 0)
    with pytest.raises(TimeValidationError) as exc_info:
        validate_local_wall_time(gap_time, "Europe/Berlin")
    assert "does not exist in timezone 'Europe/Berlin'" in str(exc_info.value)

    valid_time = datetime(2027, 3, 28, 9, 0, 0)
    validate_local_wall_time(valid_time, "Europe/Berlin")


def test_validate_local_wall_time_accepts_fall_back_fold():
    """verifies that ambiguous times during fall-back transitions are valid"""
    fold_time = datetime(2026, 10, 25, 2, 30, 0)
    validate_local_wall_time(fold_time, "Europe/Berlin")


def test_denver_dst_transition_preserves_wall_clock_time():
    """verifies denver recurring meetings retain 09:00:00 wall-clock time across 2026-11-01 dst transition"""
    start_dt = datetime(2026, 10, 21, 9, 0, 0)
    end_dt = datetime(2026, 10, 21, 10, 0, 0)
    repeat_until = date(2026, 11, 18)

    occurrences = generate_weekly_occurrences(
        start_dt=start_dt,
        end_dt=end_dt,
        repeat_until=repeat_until,
        tz_name="America/Denver",
    )

    assert len(occurrences) == 5
    for occ_start, occ_end in occurrences:
        assert occ_start.hour == 9
        assert occ_start.minute == 0
        assert occ_start.second == 0
        assert occ_end.hour == 10
        assert occ_end.minute == 0
        assert occ_end.second == 0

    expected_dates = [
        date(2026, 10, 21),
        date(2026, 10, 28),
        date(2026, 11, 4),
        date(2026, 11, 11),
        date(2026, 11, 18),
    ]
    actual_dates = [occ[0].date() for occ in occurrences]
    assert actual_dates == expected_dates


def test_berlin_dst_transition_preserves_wall_clock_time():
    """verifies berlin recurring meetings retain 09:00:00 wall-clock time across 2026-10-25 dst transition"""
    start_dt = datetime(2026, 10, 14, 9, 0, 0)
    end_dt = datetime(2026, 10, 14, 10, 0, 0)
    repeat_until = date(2026, 11, 11)

    occurrences = generate_weekly_occurrences(
        start_dt=start_dt,
        end_dt=end_dt,
        repeat_until=repeat_until,
        tz_name="Europe/Berlin",
    )

    assert len(occurrences) == 5
    for occ_start, occ_end in occurrences:
        assert occ_start.hour == 9
        assert occ_start.minute == 0
        assert occ_end.hour == 10
        assert occ_end.minute == 0


def test_generate_weekly_occurrences_boundary_validations():
    """verifies boundary checks for start/end and repeat_until dates"""
    valid_start = datetime(2026, 10, 21, 9, 0, 0)
    valid_end = datetime(2026, 10, 21, 10, 0, 0)

    # end before start
    with pytest.raises(TimeValidationError):
        generate_weekly_occurrences(
            start_dt=valid_end,
            end_dt=valid_start,
            repeat_until=date(2026, 10, 28),
            tz_name="Europe/Berlin",
        )

    # repeat_until earlier than start date
    with pytest.raises(TimeValidationError):
        generate_weekly_occurrences(
            start_dt=valid_start,
            end_dt=valid_end,
            repeat_until=date(2026, 10, 20),
            tz_name="Europe/Berlin",
        )

    # repeat_until earlier than meeting end date
    overnight_start = datetime(2026, 10, 21, 23, 0, 0)
    overnight_end = datetime(2026, 10, 22, 1, 0, 0)
    with pytest.raises(TimeValidationError) as exc_info:
        generate_weekly_occurrences(
            start_dt=overnight_start,
            end_dt=overnight_end,
            repeat_until=date(2026, 10, 21),
            tz_name="Europe/Berlin",
        )
    assert "earlier than meeting end date" in str(exc_info.value)

    # duration exceeds 7 days
    long_end = datetime(2026, 10, 29, 9, 0, 0)
    with pytest.raises(TimeValidationError) as exc_info_7d:
        generate_weekly_occurrences(
            start_dt=valid_start,
            end_dt=long_end,
            repeat_until=date(2026, 11, 21),
            tz_name="Europe/Berlin",
        )
    assert "must be less than 7 days" in str(exc_info_7d.value)


def test_generate_weekly_occurrences_allows_multiday_under_7_days():
    """verifies that multi-day meetings (e.g. 48 hours) are permitted when repeat_until >= end_dt.date()"""
    start_dt = datetime(2026, 11, 5, 0, 0, 0)
    end_dt = datetime(2026, 11, 7, 0, 0, 0)
    repeat_until = date(2026, 11, 14)

    occurrences = generate_weekly_occurrences(
        start_dt=start_dt,
        end_dt=end_dt,
        repeat_until=repeat_until,
        tz_name="Europe/Berlin",
    )
    assert len(occurrences) == 2
    assert occurrences[0] == (start_dt, end_dt)
    assert occurrences[1] == (
        datetime(2026, 11, 12, 0, 0, 0),
        datetime(2026, 11, 14, 0, 0, 0),
    )


def test_generate_weekly_occurrences_truncates_when_instance_ends_after_cutoff():
    """verifies that an occurrence is excluded if its end date exceeds repeat_until"""
    start_dt = datetime(2026, 10, 21, 23, 0, 0)
    end_dt = datetime(2026, 10, 22, 1, 0, 0)
    # repeat_until allows the first instance (ending 2026-10-22), but not the second (ending 2026-10-29)
    repeat_until = date(2026, 10, 28)

    occurrences = generate_weekly_occurrences(
        start_dt=start_dt,
        end_dt=end_dt,
        repeat_until=repeat_until,
        tz_name="Europe/Berlin",
    )
    assert len(occurrences) == 1
    assert occurrences[0][0] == start_dt
    assert occurrences[0][1] == end_dt
