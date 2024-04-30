from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.decon.a0 import (
    ELEVATED_FLOOR,
    ROUTINE_FLOOR,
    a0_of_hold,
    a0_of_trace,
    evaluate,
    hold_for,
    lethal_rate,
    temperature_for,
)
from sterilot.errors import ValidationError
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

START = datetime(2024, 5, 1, 9, 0)


def test_the_reference_temperature_earns_one_for_one() -> None:
    assert lethal_rate(Temperature(80.0)) == pytest.approx(1.0)


def test_ten_degrees_up_earns_ten_times_as_much() -> None:
    assert lethal_rate(Temperature(90.0)) == pytest.approx(10.0)
    assert lethal_rate(Temperature(70.0)) == pytest.approx(0.1)


def test_a_negative_z_is_refused() -> None:
    with pytest.raises(ValidationError):
        lethal_rate(Temperature(90.0), z=0.0)


def test_the_textbook_holds() -> None:
    assert a0_of_hold(Temperature(90.0), Duration.of_minutes(5)) == pytest.approx(3000.0)
    assert a0_of_hold(Temperature(80.0), Duration.of_minutes(10)) == pytest.approx(600.0)


def test_a_square_trace_matches_the_square_formula() -> None:
    trace = Trace.flat(START, 90.0, 300.0, step=15.0)
    assert a0_of_trace(trace) == pytest.approx(3000.0, rel=1e-6)


def test_a_ramp_earns_less_than_its_peak_would_suggest() -> None:
    trace = Trace.from_pairs(START, [(0.0, 20.0), (120.0, 90.0), (420.0, 90.0)])
    value = a0_of_trace(trace)
    assert value < a0_of_hold(Temperature(90.0), Duration.of_seconds(420.0))
    assert value > a0_of_hold(Temperature(90.0), Duration.of_seconds(300.0))


def test_hold_for_inverts_the_square_case() -> None:
    assert hold_for(Temperature(90.0), 3000.0).seconds == pytest.approx(300.0)
    assert hold_for(Temperature(80.0), 600.0).minutes == pytest.approx(10.0)


def test_hold_for_refuses_a_target_of_nothing() -> None:
    with pytest.raises(ValidationError):
        hold_for(Temperature(90.0), 0.0)


def test_temperature_for_inverts_the_other_way() -> None:
    reading = temperature_for(Duration.of_minutes(5), 3000.0)
    assert reading.celsius == pytest.approx(90.0)


def test_temperature_for_refuses_a_hold_of_nothing() -> None:
    with pytest.raises(ValidationError):
        temperature_for(Duration.zero(), 600.0)
    with pytest.raises(ValidationError):
        temperature_for(Duration.of_minutes(5), 0.0)


def test_a_clean_cycle_clears_the_routine_floor() -> None:
    trace = Trace.flat(START, 90.0, 300.0, step=30.0)
    result = evaluate(trace)
    assert result.passed
    assert result.floor == pytest.approx(ROUTINE_FLOOR)
    assert result.shortfall == pytest.approx(0.0)
    assert result.explain() == "A0 3000 clears the floor of 600"


def test_a_tired_element_shows_up_as_a_shortfall() -> None:
    trace = Trace.flat(START, 76.0, 300.0, step=30.0)
    result = evaluate(trace)
    assert not result.passed
    assert result.shortfall > 400
    assert "short of the floor" in result.explain()
    assert "76.0 C" in result.explain()


def test_the_elevated_floor_fails_a_cycle_that_passed_the_routine_one() -> None:
    trace = Trace.flat(START, 90.0, 300.0, step=30.0)
    assert evaluate(trace, ROUTINE_FLOOR).passed
    assert not evaluate(trace, ELEVATED_FLOOR * 2).passed


def test_the_result_carries_the_peak_and_the_time_above_reference() -> None:
    trace = Trace.from_pairs(START, [(0.0, 20.0), (100.0, 90.0), (400.0, 90.0)])
    result = evaluate(trace)
    assert result.peak == Temperature(90.0)
    assert result.time_above_reference.seconds > 300.0


def test_a_floor_of_nothing_is_refused() -> None:
    with pytest.raises(ValidationError):
        evaluate(Trace.flat(START, 90.0, 60.0), floor=0.0)


def test_the_reading_carries_the_band_for_a_report() -> None:
    result = evaluate(Trace.flat(START, 90.0, 300.0, step=30.0))
    assert result.reading.band.label == "A0"
    assert result.reading.passed
