from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.interval import DateRange, Window, covering


def test_a_range_must_end_after_it_starts() -> None:
    with pytest.raises(ValidationError):
        DateRange(date(2024, 3, 1), date(2024, 3, 1))
    with pytest.raises(ValidationError):
        DateRange(date(2024, 3, 2), date(2024, 3, 1))


def test_an_open_range_is_still_current() -> None:
    window = DateRange.starting(date(2024, 3, 1))
    assert window.open_ended
    assert window.days() is None
    assert window.last_day is None
    assert window.contains(date(2030, 1, 1))


def test_of_days_counts_whole_days() -> None:
    window = DateRange.of_days(date(2024, 3, 1), 30)
    assert window.end == date(2024, 3, 31)
    assert window.days() == 30
    assert window.last_day == date(2024, 3, 30)


def test_of_days_refuses_a_zero_length() -> None:
    with pytest.raises(ValidationError):
        DateRange.of_days(date(2024, 3, 1), 0)


def test_contains_is_half_open() -> None:
    window = DateRange(date(2024, 3, 1), date(2024, 4, 1))
    assert window.contains(date(2024, 3, 1))
    assert window.contains(date(2024, 3, 31))
    assert not window.contains(date(2024, 4, 1))
    assert not window.contains(date(2024, 2, 29))


def test_overlaps() -> None:
    first = DateRange(date(2024, 3, 1), date(2024, 4, 1))
    touching = DateRange(date(2024, 4, 1), date(2024, 5, 1))
    inside = DateRange(date(2024, 3, 10), date(2024, 3, 20))
    assert not first.overlaps(touching)
    assert first.overlaps(inside)
    assert inside.overlaps(first)


def test_two_open_ranges_always_overlap() -> None:
    assert DateRange.starting(date(2024, 1, 1)).overlaps(DateRange.starting(date(2030, 1, 1)))


def test_intersection() -> None:
    first = DateRange(date(2024, 3, 1), date(2024, 4, 1))
    second = DateRange(date(2024, 3, 15), date(2024, 5, 1))
    assert first.intersection(second) == DateRange(date(2024, 3, 15), date(2024, 4, 1))
    assert first.intersection(DateRange(date(2025, 1, 1), date(2025, 2, 1))) is None


def test_intersection_of_open_ranges_stays_open() -> None:
    first = DateRange.starting(date(2024, 3, 1))
    second = DateRange.starting(date(2024, 6, 1))
    assert first.intersection(second) == DateRange.starting(date(2024, 6, 1))


def test_closed_at_retires_a_revision() -> None:
    window = DateRange.starting(date(2024, 3, 1))
    assert window.closed_at(date(2024, 9, 1)).end == date(2024, 9, 1)


def test_iter_days_walks_the_window() -> None:
    days = list(DateRange.of_days(date(2024, 3, 1), 3).iter_days())
    assert days == [date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 3)]


def test_iter_days_refuses_an_open_range() -> None:
    with pytest.raises(ValidationError):
        list(DateRange.starting(date(2024, 3, 1)).iter_days())


def test_range_formatting() -> None:
    assert str(DateRange.starting(date(2024, 3, 1))) == "2024-03-01 onward"
    assert str(DateRange.of_days(date(2024, 3, 1), 2)) == "2024-03-01 to 2024-03-02"


def test_window_must_not_run_backwards() -> None:
    with pytest.raises(ValidationError):
        Window(datetime(2024, 3, 1, 10), datetime(2024, 3, 1, 9))


def test_window_lengths() -> None:
    window = Window.of_minutes(datetime(2024, 3, 1, 10), 4)
    assert window.end == datetime(2024, 3, 1, 10, 4)
    assert window.seconds == pytest.approx(240.0)
    assert window.minutes == pytest.approx(4.0)


def test_window_of_hours() -> None:
    window = Window.of_hours(datetime(2024, 3, 1, 10), 24)
    assert window.end == datetime(2024, 3, 2, 10)


def test_window_refuses_negative_minutes() -> None:
    with pytest.raises(ValidationError):
        Window.of_minutes(datetime(2024, 3, 1, 10), -1)


def test_window_contains_is_half_open() -> None:
    window = Window.of_minutes(datetime(2024, 3, 1, 10), 4)
    assert window.contains(datetime(2024, 3, 1, 10))
    assert not window.contains(datetime(2024, 3, 1, 10, 4))


def test_window_overlaps_and_extends() -> None:
    first = Window.of_minutes(datetime(2024, 3, 1, 10), 30)
    second = Window.of_minutes(datetime(2024, 3, 1, 10, 20), 30)
    assert first.overlaps(second)
    assert not first.overlaps(Window.of_minutes(datetime(2024, 3, 1, 11), 5))
    assert first.extended_by(30).end == datetime(2024, 3, 1, 11)


def test_window_formatting() -> None:
    window = Window.of_minutes(datetime(2024, 3, 1, 10), 30)
    assert str(window) == "2024-03-01 10:00 to 2024-03-01 10:30"


def test_covering_takes_the_outer_bounds() -> None:
    ranges = [
        DateRange(date(2024, 3, 1), date(2024, 4, 1)),
        DateRange(date(2024, 2, 1), date(2024, 2, 15)),
    ]
    assert covering(ranges) == DateRange(date(2024, 2, 1), date(2024, 4, 1))


def test_covering_stays_open_when_any_range_is_open() -> None:
    ranges = [DateRange(date(2024, 3, 1), date(2024, 4, 1)), DateRange.starting(date(2024, 5, 1))]
    assert covering(ranges) == DateRange.starting(date(2024, 3, 1))


def test_covering_refuses_nothing() -> None:
    with pytest.raises(ValidationError):
        covering([])
