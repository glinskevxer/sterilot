from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.sterilizer.lethality import (
    STEAROTHERMOPHILUS_D121,
    TERMINAL_FLOOR_MINUTES,
    equivalent_temperature,
    evaluate,
    f0_for_sterility,
    f0_of_hold,
    f0_of_trace,
    hold_for,
    lethal_rate,
    log_reduction,
    survival_level,
)
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

START = datetime(2024, 5, 1, 9, 0)


def test_the_reference_temperature_earns_one_for_one() -> None:
    assert lethal_rate(Temperature(121.1)) == pytest.approx(1.0)


def test_ten_degrees_is_a_factor_of_ten() -> None:
    assert lethal_rate(Temperature(131.1)) == pytest.approx(10.0)
    assert lethal_rate(Temperature(111.1)) == pytest.approx(0.1)


def test_a_bad_z_value_is_refused() -> None:
    with pytest.raises(ValidationError):
        lethal_rate(Temperature(134.0), z=-1.0)


def test_the_gravity_cycle_earns_about_its_own_length() -> None:
    value = f0_of_hold(Temperature(121.1), Duration.of_minutes(30))
    assert value == pytest.approx(30.0)


def test_the_short_prevac_cycle_is_not_the_weak_one() -> None:
    short = f0_of_hold(Temperature(134.0), Duration.of_minutes(3))
    long = f0_of_hold(Temperature(121.1), Duration.of_minutes(30))
    assert short > long
    assert short == pytest.approx(58.6, rel=0.01)


def test_a_flat_trace_matches_the_square_formula() -> None:
    trace = Trace.flat(START, 134.0, 180.0, step=10.0)
    assert f0_of_trace(trace) == pytest.approx(f0_of_hold(Temperature(134.0), Duration(180.0)))


def test_a_ramped_trace_earns_less_than_a_square_one() -> None:
    ramp = Trace.from_pairs(START, [(0.0, 100.0), (120.0, 134.0), (300.0, 134.0)])
    assert f0_of_trace(ramp) < f0_of_hold(Temperature(134.0), Duration(300.0))


def test_hold_for_inverts_the_square_case() -> None:
    assert hold_for(Temperature(121.1), 15.0).minutes == pytest.approx(15.0)
    assert hold_for(Temperature(131.1), 15.0).minutes == pytest.approx(1.5)


def test_hold_for_refuses_a_target_of_nothing() -> None:
    with pytest.raises(ValidationError):
        hold_for(Temperature(134.0), 0.0)


def test_log_reduction_divides_by_the_d_value() -> None:
    assert log_reduction(15.0) == pytest.approx(10.0)
    assert log_reduction(15.0, d_value=3.0) == pytest.approx(5.0)


def test_log_reduction_refuses_nonsense() -> None:
    with pytest.raises(ValidationError):
        log_reduction(15.0, d_value=0.0)
    with pytest.raises(ValidationError):
        log_reduction(-1.0)


def test_a_million_spores_and_ten_reductions_leaves_one_in_ten_thousand() -> None:
    assert survival_level(6.0, 15.0) == pytest.approx(-4.0)


def test_the_f0_needed_for_a_six_log_assurance() -> None:
    needed = f0_for_sterility(6.0)
    assert needed == pytest.approx(12.0 * STEAROTHERMOPHILUS_D121)
    assert survival_level(6.0, needed) == pytest.approx(-6.0)


def test_a_target_above_the_population_is_refused() -> None:
    with pytest.raises(ValidationError):
        f0_for_sterility(6.0, target_level=7.0)


def test_a_terminal_cycle_clears_the_floor() -> None:
    trace = Trace.flat(START, 134.0, 240.0, step=20.0)
    result = evaluate(trace)
    assert result.passed
    assert result.floor == pytest.approx(TERMINAL_FLOOR_MINUTES)
    assert "log reductions" in result.explain()


def test_a_cold_cycle_falls_short_and_says_so() -> None:
    trace = Trace.flat(START, 115.0, 300.0, step=30.0)
    result = evaluate(trace)
    assert not result.passed
    assert result.shortfall > 0
    assert "short of" in result.explain()
    assert "115.0 C" in result.explain()


def test_the_result_carries_the_time_above_the_reference() -> None:
    trace = Trace.from_pairs(START, [(0.0, 100.0), (60.0, 134.0), (300.0, 134.0)])
    result = evaluate(trace)
    assert result.time_above_reference.seconds > 240.0
    assert result.peak == Temperature(134.0)


def test_a_floor_of_nothing_is_refused() -> None:
    with pytest.raises(ValidationError):
        evaluate(Trace.flat(START, 134.0, 60.0), floor=0.0)


def test_equivalent_temperature_inverts_a_hold() -> None:
    reading = equivalent_temperature(Duration.of_minutes(3), 58.6)
    assert reading.celsius == pytest.approx(134.0, abs=0.05)


def test_equivalent_temperature_refuses_nonsense() -> None:
    with pytest.raises(ValidationError):
        equivalent_temperature(Duration.zero(), 15.0)
    with pytest.raises(ValidationError):
        equivalent_temperature(Duration.of_minutes(3), 0.0)


def test_the_result_reading_carries_a_band_for_a_report() -> None:
    result = evaluate(Trace.flat(START, 134.0, 240.0, step=20.0))
    assert result.reading.band.label == "F0"
    assert result.log_reductions() > 10
