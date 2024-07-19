"""The lethality integral, which the washers and the sterilizers both use.

A0 and F0 are the same calculation with different constants. A0 counts seconds
against eighty degrees for thermal disinfection, F0 counts minutes against
121.1 for steam sterilization, and both of them are the integral of a rate that
rises by a factor of ten every z degrees.

Keeping one copy of that means a fix to the integration lands on both sides of
the department, and it means the two modules above are about what the numbers
are for rather than about arithmetic.
"""

from __future__ import annotations

import math

from sterilot.errors import ValidationError
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


def rate(reading: Temperature, reference: float, z: float) -> float:
    """Seconds of credit each real second earns at ``reading``."""
    if z <= 0:
        raise ValidationError("the z value has to be positive", z=z)
    return float(10.0 ** ((reading.celsius - reference) / z))


def of_hold(reading: Temperature, held: Duration, reference: float, z: float) -> float:
    """Equivalent seconds for a square hold."""
    return rate(reading, reference, z) * held.seconds


def of_trace(trace: Trace, reference: float, z: float) -> float:
    """Equivalent seconds integrated over a trace."""
    return trace.integrate(lambda reading: rate(reading, reference, z))


def hold_for(reading: Temperature, target_seconds: float, reference: float, z: float) -> Duration:
    """How long ``reading`` has to be held to earn ``target_seconds``."""
    if target_seconds <= 0:
        raise ValidationError("a lethality target is a positive number", target=target_seconds)
    earned = rate(reading, reference, z)
    if earned <= 0:
        raise ValidationError("that temperature earns no credit", celsius=reading.celsius)
    return Duration(target_seconds / earned)


def flat_temperature(
    held: Duration, target_seconds: float, reference: float, z: float
) -> Temperature:
    """The flat temperature that earns ``target_seconds`` in ``held``."""
    if held.seconds <= 0:
        raise ValidationError("a hold has to last", seconds=held.seconds)
    if target_seconds <= 0:
        raise ValidationError("a lethality target is a positive number", target=target_seconds)
    if z <= 0:
        raise ValidationError("the z value has to be positive", z=z)
    return Temperature(reference + z * math.log10(target_seconds / held.seconds))
