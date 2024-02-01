from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.units.duration import Duration, longest, total


def test_seconds_are_kept_as_given() -> None:
    assert Duration(240.0).seconds == pytest.approx(240.0)


def test_negative_is_refused() -> None:
    with pytest.raises(ValidationError):
        Duration(-1.0)


def test_constructors() -> None:
    assert Duration.of_minutes(4).seconds == pytest.approx(240.0)
    assert Duration.of_hours(1.5).seconds == pytest.approx(5400.0)
    assert Duration.zero().seconds == 0.0
    assert Duration.of_seconds(12).seconds == pytest.approx(12.0)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("00:04:00", 240.0),
        ("4:00", 240.0),
        ("1:02:03", 3723.0),
        ("0:00:30.5", 30.5),
        ("47 min", 2820.0),
        ("47min", 2820.0),
        ("2h 30m", 9000.0),
        ("90s", 90.0),
        ("1 hour", 3600.0),
        ("3 minutes 20 seconds", 200.0),
    ],
)
def test_parse_reads_every_printer(text: str, seconds: float) -> None:
    assert Duration.parse(text).seconds == pytest.approx(seconds)


def test_bare_number_takes_the_unit_the_caller_names() -> None:
    assert Duration.parse("240").seconds == pytest.approx(240.0)
    assert Duration.parse("240", bare_unit="m").seconds == pytest.approx(14400.0)
    assert Duration.parse("2", bare_unit="h").seconds == pytest.approx(7200.0)


def test_bare_unit_must_be_one_we_know() -> None:
    with pytest.raises(ValidationError):
        Duration.parse("240", bare_unit="d")


@pytest.mark.parametrize("text", ["", "soon", "4:70", "0:99:00", "abc s"])
def test_parse_refuses_nonsense(text: str) -> None:
    with pytest.raises(ValidationError):
        Duration.parse(text)


def test_minutes_and_hours_are_views() -> None:
    span = Duration(5400.0)
    assert span.minutes == pytest.approx(90.0)
    assert span.hours == pytest.approx(1.5)


def test_arithmetic() -> None:
    assert (Duration(60) + Duration(30)).seconds == pytest.approx(90.0)
    assert (Duration(60) - Duration(30)).seconds == pytest.approx(30.0)
    assert (Duration(60) * 3).seconds == pytest.approx(180.0)


def test_subtraction_below_zero_is_refused() -> None:
    with pytest.raises(ValidationError):
        Duration(30) - Duration(60)


def test_truthiness_follows_the_clock() -> None:
    assert Duration(1)
    assert not Duration.zero()


def test_shortfall_is_zero_when_the_floor_is_met() -> None:
    assert Duration(240).shortfall_against(Duration(240)) == Duration.zero()
    assert Duration(250).shortfall_against(Duration(240)) == Duration.zero()


def test_shortfall_reports_the_gap() -> None:
    assert Duration(200).shortfall_against(Duration(240)).seconds == pytest.approx(40.0)


def test_clamp() -> None:
    assert Duration(10).clamp(Duration(20), Duration(40)) == Duration(20)
    assert Duration(50).clamp(Duration(20), Duration(40)) == Duration(40)
    assert Duration(30).clamp(Duration(20), Duration(40)) == Duration(30)


def test_clamp_refuses_inverted_bounds() -> None:
    with pytest.raises(ValidationError):
        Duration(30).clamp(Duration(40), Duration(20))


def test_rounded() -> None:
    assert Duration(240.4).rounded() == Duration(240.0)
    assert Duration(240.456).rounded(2) == Duration(240.46)


@pytest.mark.parametrize(
    ("seconds", "clock", "spelled"),
    [
        (0.0, "0:00:00", "0s"),
        (240.0, "0:04:00", "4m"),
        (3723.0, "1:02:03", "1h 2m 3s"),
        (90.0, "0:01:30", "1m 30s"),
        (3600.0, "1:00:00", "1h"),
    ],
)
def test_rendering(seconds: float, clock: str, spelled: str) -> None:
    span = Duration(seconds)
    assert span.clock() == clock
    assert span.spelled() == spelled
    assert str(span) == spelled


def test_ordering() -> None:
    assert Duration(30) < Duration(60)
    assert sorted([Duration(60), Duration(30)])[0] == Duration(30)


def test_total_and_longest() -> None:
    spans = [Duration(30), Duration(90), Duration(15)]
    assert total(spans) == Duration(135)
    assert longest(spans) == Duration(90)
    assert total([]) == Duration.zero()


def test_longest_refuses_an_empty_run() -> None:
    with pytest.raises(ValidationError):
        longest([])
