from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.units.temperature import Temperature, coldest, hottest


def test_stores_celsius_as_given() -> None:
    assert Temperature(134.0).celsius == pytest.approx(134.0)


def test_fahrenheit_round_trips() -> None:
    reading = Temperature.from_fahrenheit(273.2)
    assert reading.celsius == pytest.approx(134.0, abs=0.01)
    assert reading.fahrenheit == pytest.approx(273.2, abs=0.01)


def test_kelvin_round_trips() -> None:
    reading = Temperature.from_kelvin(407.15)
    assert reading.celsius == pytest.approx(134.0)
    assert reading.kelvin == pytest.approx(407.15)


def test_below_absolute_zero_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        Temperature(-300.0)
    assert caught.value.context["celsius"] == -300.0


def test_absurdly_hot_is_refused() -> None:
    with pytest.raises(ValidationError):
        Temperature(900.0)


def test_absolute_zero_itself_is_allowed() -> None:
    assert Temperature(-273.15).kelvin == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("text", "celsius"),
    [
        ("134", 134.0),
        ("134C", 134.0),
        ("134 c", 134.0),
        ("  121.1  C ", 121.1),
        ("273.2F", 134.0),
        ("60 deg C", 60.0),
        ("407.15K", 134.0),
        ("-40F", -40.0),
    ],
)
def test_parse_reads_the_shapes_the_printers_use(text: str, celsius: float) -> None:
    assert Temperature.parse(text).celsius == pytest.approx(celsius, abs=0.01)


@pytest.mark.parametrize("text", ["", "hot", "134 X", "12 34", "C134"])
def test_parse_refuses_anything_else(text: str) -> None:
    with pytest.raises(ValidationError):
        Temperature.parse(text)


def test_difference_is_signed() -> None:
    assert Temperature(134.0).difference(Temperature(132.0)) == pytest.approx(2.0)
    assert Temperature(132.0).difference(Temperature(134.0)) == pytest.approx(-2.0)


def test_offset_by_moves_the_reading() -> None:
    assert Temperature(134.0).offset_by(-3.0) == Temperature(131.0)


def test_within_uses_absolute_distance() -> None:
    assert Temperature(134.0).within(Temperature(133.0), 1.0)
    assert Temperature(133.0).within(Temperature(134.0), 1.0)
    assert not Temperature(134.0).within(Temperature(132.0), 1.0)


def test_within_refuses_a_negative_tolerance() -> None:
    with pytest.raises(ValidationError):
        Temperature(134.0).within(Temperature(134.0), -1.0)


def test_is_at_least_is_inclusive() -> None:
    assert Temperature(134.0).is_at_least(Temperature(134.0))
    assert Temperature(134.1).is_at_least(Temperature(134.0))
    assert not Temperature(133.9).is_at_least(Temperature(134.0))


def test_ordering_and_equality() -> None:
    assert Temperature(121.1) < Temperature(134.0)
    assert Temperature(134.0) == Temperature(134.0)
    assert sorted([Temperature(134.0), Temperature(121.1)])[0] == Temperature(121.1)


def test_rounded_trims_the_printer_noise() -> None:
    assert Temperature(134.04999).rounded() == Temperature(134.0)
    assert Temperature(134.04999).rounded(3) == Temperature(134.05)


def test_format_in_each_unit() -> None:
    reading = Temperature(134.0)
    assert reading.format() == "134.0 C"
    assert reading.format("F") == "273.2 F"
    assert reading.format("k", places=2) == "407.15 K"
    assert str(reading) == "134.0 C"


def test_format_refuses_an_unknown_unit() -> None:
    with pytest.raises(ValidationError):
        Temperature(134.0).format("R")


def test_hottest_and_coldest() -> None:
    readings = [Temperature(131.0), Temperature(135.2), Temperature(133.4)]
    assert hottest(readings) == Temperature(135.2)
    assert coldest(readings) == Temperature(131.0)


def test_hottest_and_coldest_refuse_an_empty_run() -> None:
    with pytest.raises(ValidationError):
        hottest([])
    with pytest.raises(ValidationError):
        coldest([])


def test_the_sanity_ceiling_itself_is_allowed() -> None:
    assert Temperature(400.0).celsius == pytest.approx(400.0)


def test_a_reading_just_over_the_ceiling_names_it() -> None:
    with pytest.raises(ValidationError) as caught:
        Temperature(400.1)
    assert caught.value.context["ceiling"] == 400.0


def test_offsetting_past_the_ceiling_is_refused() -> None:
    with pytest.raises(ValidationError):
        Temperature(390.0).offset_by(20.0)


def test_a_tolerance_of_nothing_is_an_exact_match() -> None:
    assert Temperature(134.0).within(Temperature(134.0), 0.0)
    assert not Temperature(134.0).within(Temperature(134.1), 0.0)
