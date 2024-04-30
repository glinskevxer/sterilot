"""The A0 value: how much thermal disinfection a wash cycle actually delivered.

A0 is the equivalent number of seconds at eighty degrees, with every degree
above that counting ten times as much per ten degrees. Ninety degrees for five
minutes is an A0 of three thousand. Eighty degrees for ten minutes is six
hundred. The department runs six hundred as the floor for instruments going to
the assembly bench and three thousand for anything that touched a patient's
blood in a case flagged for it.

The reason to compute it rather than read the setpoint off the front panel is
that the setpoint is what the machine was asked for. A0 is what the load got,
and on a machine with a tired heating element those are different numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sterilot.errors import ValidationError
from sterilot.tolerance import Band, Reading
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

REFERENCE_C = 80.0
Z_VALUE = 10.0

ROUTINE_FLOOR = 600.0
"""A0 the department requires for instruments going on to assembly."""

ELEVATED_FLOOR = 3000.0
"""A0 required when the case notes call for it."""


def lethal_rate(reading: Temperature, reference: float = REFERENCE_C, z: float = Z_VALUE) -> float:
    """Seconds of credit each real second earns at ``reading``."""
    if z <= 0:
        raise ValidationError("the z value has to be positive", z=z)
    return float(10.0 ** ((reading.celsius - reference) / z))


def a0_of_hold(
    reading: Temperature,
    held: Duration,
    reference: float = REFERENCE_C,
    z: float = Z_VALUE,
) -> float:
    """A0 for a square hold, which is what a spec sheet describes."""
    return lethal_rate(reading, reference, z) * held.seconds


def a0_of_trace(trace: Trace, reference: float = REFERENCE_C, z: float = Z_VALUE) -> float:
    """A0 integrated over a real trace."""
    return trace.integrate(lambda reading: lethal_rate(reading, reference, z))


def hold_for(
    reading: Temperature,
    target: float,
    reference: float = REFERENCE_C,
    z: float = Z_VALUE,
) -> Duration:
    """How long ``reading`` has to be held to reach ``target``."""
    if target <= 0:
        raise ValidationError("an A0 target is a positive number", target=target)
    rate = lethal_rate(reading, reference, z)
    if rate <= 0:
        raise ValidationError("that temperature earns no credit", celsius=reading.celsius)
    return Duration(target / rate)


def temperature_for(
    held: Duration,
    target: float,
    reference: float = REFERENCE_C,
    z: float = Z_VALUE,
) -> Temperature:
    """The flat temperature that reaches ``target`` in ``held``."""
    if held.seconds <= 0:
        raise ValidationError("a hold has to last", seconds=held.seconds)
    if target <= 0:
        raise ValidationError("an A0 target is a positive number", target=target)
    return Temperature(reference + z * math.log10(target / held.seconds))


@dataclass(frozen=True)
class A0Result:
    """An A0 measurement judged against the floor that applied."""

    value: float
    floor: float
    peak: Temperature
    time_above_reference: Duration

    @property
    def reading(self) -> Reading:
        return Band.at_least(self.floor, label="A0").evaluate(self.value)

    @property
    def passed(self) -> bool:
        return self.reading.passed

    @property
    def shortfall(self) -> float:
        return max(self.floor - self.value, 0.0)

    def explain(self) -> str:
        if self.passed:
            return f"A0 {self.value:.0f} clears the floor of {self.floor:.0f}"
        return (
            f"A0 {self.value:.0f} is {self.shortfall:.0f} short of the floor of {self.floor:.0f}, "
            f"peak {self.peak.format()}"
        )

    def __str__(self) -> str:
        return self.explain()


def evaluate(trace: Trace, floor: float = ROUTINE_FLOOR) -> A0Result:
    """Score a wash trace against an A0 floor."""
    if floor <= 0:
        raise ValidationError("an A0 floor is a positive number", floor=floor)
    return A0Result(
        value=a0_of_trace(trace),
        floor=floor,
        peak=trace.peak(),
        time_above_reference=trace.time_above(Temperature(REFERENCE_C)),
    )
