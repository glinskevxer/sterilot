from __future__ import annotations

from datetime import datetime

import pytest

from sterilot import lethality
from sterilot.errors import ValidationError
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

START = datetime(2024, 8, 1, 9, 0)


def test_the_reference_temperature_earns_one_for_one() -> None:
    assert lethality.rate(Temperature(80.0), 80.0, 10.0) == pytest.approx(1.0)


def test_the_rate_climbs_by_a_factor_of_ten_every_z_degrees() -> None:
    assert lethality.rate(Temperature(90.0), 80.0, 10.0) == pytest.approx(10.0)
    assert lethality.rate(Temperature(100.0), 80.0, 20.0) == pytest.approx(10.0)


def test_a_bad_z_value_is_refused_everywhere() -> None:
    with pytest.raises(ValidationError):
        lethality.rate(Temperature(90.0), 80.0, 0.0)
    with pytest.raises(ValidationError):
        lethality.flat_temperature(Duration.of_minutes(5), 600.0, 80.0, -1.0)


def test_a_square_hold_matches_the_integral_over_a_flat_trace() -> None:
    held = Duration.of_minutes(5)
    square = lethality.of_hold(Temperature(90.0), held, 80.0, 10.0)
    trace = lethality.of_trace(Trace.flat(START, 90.0, held.seconds, step=15.0), 80.0, 10.0)
    assert square == pytest.approx(trace)


def test_hold_for_inverts_the_square_case() -> None:
    assert lethality.hold_for(Temperature(90.0), 3000.0, 80.0, 10.0).seconds == pytest.approx(300.0)


def test_flat_temperature_inverts_the_other_way() -> None:
    reading = lethality.flat_temperature(Duration.of_minutes(5), 3000.0, 80.0, 10.0)
    assert reading.celsius == pytest.approx(90.0)


def test_a_target_of_nothing_is_refused() -> None:
    with pytest.raises(ValidationError):
        lethality.hold_for(Temperature(90.0), 0.0, 80.0, 10.0)
    with pytest.raises(ValidationError):
        lethality.flat_temperature(Duration.of_minutes(5), 0.0, 80.0, 10.0)


def test_a_hold_of_nothing_is_refused() -> None:
    with pytest.raises(ValidationError):
        lethality.flat_temperature(Duration.zero(), 600.0, 80.0, 10.0)


def test_the_same_integral_serves_both_reference_temperatures() -> None:
    trace = Trace.flat(START, 121.1, 900.0, step=30.0)
    as_f0 = lethality.of_trace(trace, 121.1, 10.0) / 60.0
    as_a0 = lethality.of_trace(trace, 80.0, 10.0)
    assert as_f0 == pytest.approx(15.0)
    assert as_a0 > as_f0
