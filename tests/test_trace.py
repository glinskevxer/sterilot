from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.trace import Trace, TracePoint
from sterilot.units.temperature import Temperature

START = datetime(2024, 3, 1, 9, 0)


def ramp() -> Trace:
    return Trace.from_pairs(
        START,
        [(0.0, 20.0), (60.0, 80.0), (120.0, 134.0), (360.0, 134.0), (420.0, 100.0)],
    )


def test_a_sample_cannot_predate_the_cycle() -> None:
    with pytest.raises(ValidationError):
        TracePoint(-1.0, Temperature(20.0))


def test_a_sample_can_be_placed_on_the_clock() -> None:
    point = TracePoint(90.0, Temperature(134.0))
    assert point.moment(START) == datetime(2024, 3, 1, 9, 1, 30)


def test_a_trace_needs_two_samples() -> None:
    with pytest.raises(ValidationError):
        Trace.from_pairs(START, [(0.0, 20.0)])


def test_samples_must_step_forward() -> None:
    with pytest.raises(ValidationError):
        Trace.from_pairs(START, [(0.0, 20.0), (0.0, 21.0)])
    with pytest.raises(ValidationError):
        Trace.from_pairs(START, [(60.0, 20.0), (30.0, 21.0)])


def test_length_and_iteration() -> None:
    trace = ramp()
    assert len(trace) == 5
    assert [point.offset for point in trace] == [0.0, 60.0, 120.0, 360.0, 420.0]


def test_duration_and_finish() -> None:
    trace = ramp()
    assert trace.duration.seconds == pytest.approx(420.0)
    assert trace.finished_at == datetime(2024, 3, 1, 9, 7)


def test_peak_and_trough() -> None:
    trace = ramp()
    assert trace.peak() == Temperature(134.0)
    assert trace.trough() == Temperature(20.0)


def test_reading_at_a_sample_is_the_sample() -> None:
    assert ramp().at(120.0) == Temperature(134.0)


def test_reading_between_samples_is_interpolated() -> None:
    assert ramp().at(30.0).celsius == pytest.approx(50.0)
    assert ramp().at(390.0).celsius == pytest.approx(117.0)


def test_reading_outside_the_trace_is_refused() -> None:
    with pytest.raises(ValidationError):
        ramp().at(-1.0)
    with pytest.raises(ValidationError):
        ramp().at(421.0)


def test_time_above_counts_a_flat_top() -> None:
    trace = Trace.flat(START, 134.0, 240.0, step=30.0)
    assert trace.time_above(Temperature(134.0)).seconds == pytest.approx(240.0)


def test_time_above_interpolates_the_crossings() -> None:
    trace = Trace.from_pairs(START, [(0.0, 100.0), (100.0, 140.0), (200.0, 100.0)])
    assert trace.time_above(Temperature(120.0)).seconds == pytest.approx(100.0)


def test_time_above_is_zero_when_the_trace_never_gets_there() -> None:
    assert ramp().time_above(Temperature(200.0)).seconds == pytest.approx(0.0)


def test_integrate_of_a_constant_is_the_duration() -> None:
    trace = Trace.flat(START, 134.0, 300.0, step=60.0)
    assert trace.integrate(lambda _: 1.0) == pytest.approx(300.0)


def test_integrate_weights_by_temperature() -> None:
    trace = Trace.from_pairs(START, [(0.0, 0.0), (100.0, 100.0)])
    assert trace.integrate(lambda reading: reading.celsius) == pytest.approx(5000.0)


def test_flat_needs_a_length() -> None:
    with pytest.raises(ValidationError):
        Trace.flat(START, 134.0, 0.0)


def test_flat_ends_exactly_on_the_length() -> None:
    trace = Trace.flat(START, 134.0, 250.0, step=60.0)
    assert trace.points[-1].offset == pytest.approx(250.0)
    assert trace.duration.seconds == pytest.approx(250.0)


def test_window_trims_and_rebases() -> None:
    window = ramp().window(120.0, 360.0)
    assert window.started_at == datetime(2024, 3, 1, 9, 2)
    assert window.duration.seconds == pytest.approx(240.0)
    assert window.peak() == Temperature(134.0)


def test_window_interpolates_its_ends() -> None:
    window = ramp().window(30.0, 90.0)
    assert window.points[0].temperature.celsius == pytest.approx(50.0)
    assert window.points[-1].temperature.celsius == pytest.approx(107.0)


def test_window_refuses_an_inverted_range() -> None:
    with pytest.raises(ValidationError):
        ramp().window(300.0, 100.0)


def test_celsius_values_are_plain_floats() -> None:
    assert ramp().celsius_values()[0] == pytest.approx(20.0)
