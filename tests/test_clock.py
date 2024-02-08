from __future__ import annotations

from datetime import date, datetime, time

import pytest

from sterilot.clock import (
    Clock,
    Shift,
    day_bounds,
    format_day,
    format_moment,
    parse_day,
    parse_days,
    parse_moment,
    processing_day,
    shift_at,
    within_day,
)
from sterilot.errors import ValidationError


@pytest.mark.parametrize(
    ("clock_time", "shift"),
    [
        (time(7, 0), Shift.FIRST),
        (time(11, 30), Shift.FIRST),
        (time(14, 59), Shift.FIRST),
        (time(15, 0), Shift.SECOND),
        (time(22, 59), Shift.SECOND),
        (time(23, 0), Shift.THIRD),
        (time(2, 15), Shift.THIRD),
        (time(6, 59), Shift.THIRD),
    ],
)
def test_shift_boundaries(clock_time: time, shift: Shift) -> None:
    assert shift_at(datetime.combine(date(2024, 1, 15), clock_time)) is shift


def test_shift_labels_are_what_the_floor_calls_them() -> None:
    assert Shift.FIRST.label == "days"
    assert Shift.SECOND.label == "evenings"
    assert Shift.THIRD.label == "nights"


def test_shift_can_be_named_either_way() -> None:
    assert Shift.named("nights") is Shift.THIRD
    assert Shift.named(" THIRD ") is Shift.THIRD
    assert Shift.named("days") is Shift.FIRST


def test_unknown_shift_is_refused() -> None:
    with pytest.raises(ValidationError):
        Shift.named("swing")


def test_a_night_load_belongs_to_the_day_the_shift_started() -> None:
    assert processing_day(datetime(2024, 1, 16, 1, 30)) == date(2024, 1, 15)
    assert processing_day(datetime(2024, 1, 16, 6, 59)) == date(2024, 1, 15)


def test_the_day_rolls_over_at_seven() -> None:
    assert processing_day(datetime(2024, 1, 16, 7, 0)) == date(2024, 1, 16)
    assert processing_day(datetime(2024, 1, 16, 23, 30)) == date(2024, 1, 16)


def test_day_bounds_are_half_open() -> None:
    start, end = day_bounds(date(2024, 1, 15))
    assert start == datetime(2024, 1, 15, 7, 0)
    assert end == datetime(2024, 1, 16, 7, 0)
    assert within_day(start, date(2024, 1, 15))
    assert not within_day(end, date(2024, 1, 15))
    assert within_day(datetime(2024, 1, 16, 3, 0), date(2024, 1, 15))


@pytest.mark.parametrize(
    ("text", "moment"),
    [
        ("2024-01-15T13:45:00", datetime(2024, 1, 15, 13, 45)),
        ("2024-01-15 13:45:00", datetime(2024, 1, 15, 13, 45)),
        ("2024-01-15 13:45", datetime(2024, 1, 15, 13, 45)),
        ("2024/01/15 13:45", datetime(2024, 1, 15, 13, 45)),
        ("01/15/2024 13:45", datetime(2024, 1, 15, 13, 45)),
        ("01/15/24 13:45", datetime(2024, 1, 15, 13, 45)),
        ("  2024-01-15T13:45  ", datetime(2024, 1, 15, 13, 45)),
    ],
)
def test_parse_moment(text: str, moment: datetime) -> None:
    assert parse_moment(text) == moment


def test_parse_moment_refuses_nonsense() -> None:
    with pytest.raises(ValidationError):
        parse_moment("yesterday afternoon")


@pytest.mark.parametrize(
    ("text", "day"),
    [
        ("2024-01-15", date(2024, 1, 15)),
        ("2024/01/15", date(2024, 1, 15)),
        ("01/15/2024", date(2024, 1, 15)),
        ("01/15/24", date(2024, 1, 15)),
        ("15-Jan-2024", date(2024, 1, 15)),
    ],
)
def test_parse_day(text: str, day: date) -> None:
    assert parse_day(text) == day


def test_parse_day_refuses_nonsense() -> None:
    with pytest.raises(ValidationError):
        parse_day("the fifteenth")


@pytest.mark.parametrize(("text", "days"), [("30", 30), ("30d", 30), ("30 days", 30), ("1 day", 1)])
def test_parse_days(text: str, days: int) -> None:
    assert parse_days(text) == days


def test_parse_days_refuses_nonsense() -> None:
    with pytest.raises(ValidationError):
        parse_days("a month")


def test_formatting() -> None:
    assert format_moment(datetime(2024, 1, 15, 13, 45, 12)) == "2024-01-15 13:45"
    assert format_day(date(2024, 1, 15)) == "2024-01-15"


def test_a_pinned_clock_does_not_move() -> None:
    clock = Clock(fixed=datetime(2024, 1, 16, 2, 0))
    assert clock.now() == datetime(2024, 1, 16, 2, 0)
    assert clock.today() == date(2024, 1, 15)


def test_a_live_clock_has_no_microseconds() -> None:
    assert Clock().now().microsecond == 0


def test_at_returns_a_pinned_clock() -> None:
    clock = Clock().at(datetime(2024, 5, 1, 9, 0))
    assert clock.now() == datetime(2024, 5, 1, 9, 0)
    assert clock.today() == date(2024, 5, 1)
