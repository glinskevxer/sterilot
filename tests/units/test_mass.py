from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.units.mass import (
    SET_WEIGHT_LIMIT_KG,
    Mass,
    heaviest,
    set_weight_limit,
    total,
)


def test_kilograms_are_stored_as_given() -> None:
    assert Mass(10.4).kilograms == pytest.approx(10.4)


def test_negative_is_refused() -> None:
    with pytest.raises(ValidationError):
        Mass(-0.1)


def test_constructors_agree() -> None:
    assert Mass.of_grams(1000).kilograms == pytest.approx(1.0)
    assert Mass.of_pounds(25).kilograms == pytest.approx(11.34, abs=0.01)
    assert Mass.of_ounces(16).kilograms == pytest.approx(0.4536, abs=0.001)
    assert Mass.zero().kilograms == 0.0


def test_views_round_trip() -> None:
    weight = Mass.of_pounds(22.5)
    assert weight.pounds == pytest.approx(22.5)
    assert weight.grams == pytest.approx(weight.kilograms * 1000.0)
    assert weight.ounces == pytest.approx(22.5 * 16.0, abs=0.01)


@pytest.mark.parametrize(
    ("text", "kilograms"),
    [
        ("10.4", 10.4),
        ("10.4kg", 10.4),
        ("10.4 KG", 10.4),
        ("800 g", 0.8),
        ("25lb", 11.34),
        ("25 lbs", 11.34),
        ("12 oz", 0.34),
    ],
)
def test_parse(text: str, kilograms: float) -> None:
    assert Mass.parse(text).kilograms == pytest.approx(kilograms, abs=0.01)


@pytest.mark.parametrize("text", ["", "heavy", "-4kg", "10 stone"])
def test_parse_refuses_nonsense(text: str) -> None:
    with pytest.raises(ValidationError):
        Mass.parse(text)


def test_arithmetic() -> None:
    assert (Mass(4.0) + Mass(2.5)).kilograms == pytest.approx(6.5)
    assert (Mass(4.0) - Mass(2.5)).kilograms == pytest.approx(1.5)
    assert (Mass(4.0) * 2).kilograms == pytest.approx(8.0)


def test_subtracting_past_zero_is_refused() -> None:
    with pytest.raises(ValidationError):
        Mass(1.0) - Mass(2.0)


def test_scaling_by_a_negative_is_refused() -> None:
    with pytest.raises(ValidationError):
        Mass(1.0) * -1


def test_over_reports_the_excess() -> None:
    assert Mass(12.0).over(set_weight_limit()).kilograms == pytest.approx(0.6, abs=0.001)
    assert Mass(11.4).over(set_weight_limit()) == Mass.zero()
    assert Mass(9.0).over(set_weight_limit()) == Mass.zero()


def test_the_department_limit_is_the_documented_one() -> None:
    assert set_weight_limit().kilograms == pytest.approx(SET_WEIGHT_LIMIT_KG)
    assert set_weight_limit().pounds == pytest.approx(25.1, abs=0.1)


def test_rounded() -> None:
    assert Mass(10.4444).rounded() == Mass(10.44)
    assert Mass(10.4444).rounded(1) == Mass(10.4)


def test_format() -> None:
    weight = Mass(10.4)
    assert weight.format() == "10.40 kg"
    assert weight.format("lb", places=1) == "22.9 lb"
    assert weight.format("g", places=0) == "10400 g"
    assert weight.format("oz", places=0) == "367 oz"
    assert str(weight) == "10.40 kg"


def test_format_refuses_an_unknown_unit() -> None:
    with pytest.raises(ValidationError):
        Mass(1.0).format("stone")


def test_total_and_heaviest() -> None:
    weights = [Mass(1.0), Mass(4.5), Mass(2.0)]
    assert total(weights) == Mass(7.5)
    assert heaviest(weights) == Mass(4.5)
    assert total([]) == Mass.zero()


def test_heaviest_refuses_an_empty_run() -> None:
    with pytest.raises(ValidationError):
        heaviest([])


def test_ordering() -> None:
    assert Mass(1.0) < Mass(2.0)
    assert sorted([Mass(2.0), Mass(1.0)])[0] == Mass(1.0)
