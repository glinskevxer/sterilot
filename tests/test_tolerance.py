from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.tolerance import Band, Side


def test_a_band_needs_a_bound() -> None:
    with pytest.raises(ValidationError):
        Band()


def test_inverted_bounds_are_refused() -> None:
    with pytest.raises(ValidationError):
        Band(low=10.0, high=5.0)


def test_a_single_point_band_is_allowed() -> None:
    band = Band(low=5.0, high=5.0)
    assert band.contains(5.0)
    assert not band.contains(5.1)


def test_at_least_has_no_ceiling() -> None:
    band = Band.at_least(240.0, label="exposure")
    assert band.contains(240.0)
    assert band.contains(10_000.0)
    assert not band.contains(239.9)


def test_at_most_has_no_floor() -> None:
    band = Band.at_most(3.0, label="superheat")
    assert band.contains(-40.0)
    assert not band.contains(3.1)


def test_between_is_inclusive_on_both_ends() -> None:
    band = Band.between(134.0, 137.0)
    assert band.contains(134.0)
    assert band.contains(137.0)
    assert not band.contains(133.9)


def test_around_reads_a_spec_sheet() -> None:
    band = Band.around(134.0, 0.0, 3.0, label="chamber")
    assert band.low == pytest.approx(134.0)
    assert band.high == pytest.approx(137.0)


def test_around_defaults_to_symmetric() -> None:
    band = Band.around(60.0, 2.0)
    assert band.low == pytest.approx(58.0)
    assert band.high == pytest.approx(62.0)


def test_around_refuses_negative_magnitudes() -> None:
    with pytest.raises(ValidationError):
        Band.around(60.0, -1.0)
    with pytest.raises(ValidationError):
        Band.around(60.0, 1.0, -1.0)


@pytest.mark.parametrize(
    ("value", "side"),
    [(133.0, Side.BELOW), (134.0, Side.INSIDE), (135.5, Side.INSIDE), (140.0, Side.ABOVE)],
)
def test_side(value: float, side: Side) -> None:
    assert Band.between(134.0, 137.0).side(value) is side


def test_only_inside_is_not_a_failure() -> None:
    assert not Side.INSIDE.is_failure
    assert Side.BELOW.is_failure
    assert Side.ABOVE.is_failure


def test_deviation_is_signed_and_zero_inside() -> None:
    band = Band.between(134.0, 137.0)
    assert band.deviation(135.0) == pytest.approx(0.0)
    assert band.deviation(133.0) == pytest.approx(-1.0)
    assert band.deviation(139.0) == pytest.approx(2.0)


def test_deviation_on_an_open_side_is_zero() -> None:
    assert Band.at_least(240.0).deviation(10_000.0) == pytest.approx(0.0)


def test_widened_by_moves_both_bounds_outward() -> None:
    band = Band.between(134.0, 137.0).widened_by(1.0)
    assert band.low == pytest.approx(133.0)
    assert band.high == pytest.approx(138.0)


def test_widening_an_open_band_leaves_the_open_side_open() -> None:
    band = Band.at_least(240.0).widened_by(5.0)
    assert band.low == pytest.approx(235.0)
    assert band.high is None


def test_widening_by_a_negative_is_refused() -> None:
    with pytest.raises(ValidationError):
        Band.between(1.0, 2.0).widened_by(-1.0)


def test_band_formatting() -> None:
    assert Band.between(134.0, 137.0).format(unit="C") == "134.0 to 137.0 C"
    assert Band.at_least(240.0).format(places=0, unit="s") == "at least 240 s"
    assert Band.at_most(3.0).format() == "no more than 3.0"
    assert str(Band.between(1.0, 2.0)) == "1.0 to 2.0"


def test_evaluate_carries_the_band_along() -> None:
    reading = Band.between(134.0, 137.0, label="chamber").evaluate(135.2)
    assert reading.passed
    assert reading.value == pytest.approx(135.2)
    assert reading.band.label == "chamber"
    assert reading.deviation == pytest.approx(0.0)


def test_a_passing_reading_explains_itself() -> None:
    reading = Band.between(134.0, 137.0, label="chamber").evaluate(135.2)
    assert reading.explain(unit="C") == "chamber 135.2 C is inside 134.0 to 137.0 C"


def test_a_low_reading_names_the_gap() -> None:
    reading = Band.between(134.0, 137.0, label="chamber").evaluate(132.8)
    assert reading.explain(unit="C") == "chamber 132.8 C is 1.2 C under 134.0 to 137.0 C"


def test_a_high_reading_names_the_gap() -> None:
    reading = Band.at_most(3.0, label="superheat").evaluate(7.5)
    assert reading.explain() == "superheat 7.5 is 4.5 over no more than 3.0"


def test_an_unlabelled_reading_says_value() -> None:
    assert str(Band.at_least(1.0).evaluate(0.0)).startswith("value 0.0")
