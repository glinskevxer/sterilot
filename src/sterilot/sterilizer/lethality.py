"""F0: how much sterilization a steam cycle actually delivered.

F0 is the equivalent number of minutes at 121.1 degrees, with ten degrees worth
a factor of ten. A gravity cycle held at 121 for thirty minutes has an F0 of
about thirty. A prevacuum cycle at 134 for three minutes has an F0 near sixty,
which is why the short cycle is not the weak one.

Once F0 is in hand the rest is arithmetic on the resistance of the organism
being killed. Geobacillus stearothermophilus, which is what the biological
indicators carry, has a D value near a minute and a half at 121, so an F0 of
fifteen is ten log reductions and an F0 of sixty is forty.
"""

from __future__ import annotations

from dataclasses import dataclass

from sterilot import lethality
from sterilot.errors import ValidationError
from sterilot.tolerance import Band, Reading
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

REFERENCE_C = 121.1
Z_VALUE = 10.0

STEAROTHERMOPHILUS_D121 = 1.5
"""Minutes at 121.1 to kill ninety percent of the spores on an indicator."""

TERMINAL_FLOOR_MINUTES = 15.0
"""The department's F0 floor for a load going to storage."""


def lethal_rate(reading: Temperature, reference: float = REFERENCE_C, z: float = Z_VALUE) -> float:
    """Minutes of credit each real minute earns at ``reading``."""
    return lethality.rate(reading, reference, z)


def f0_of_hold(
    reading: Temperature,
    held: Duration,
    reference: float = REFERENCE_C,
    z: float = Z_VALUE,
) -> float:
    """F0 in minutes for a square hold."""
    return lethality.of_hold(reading, held, reference, z) / 60.0


def f0_of_trace(trace: Trace, reference: float = REFERENCE_C, z: float = Z_VALUE) -> float:
    """F0 in minutes, integrated over a real trace."""
    return lethality.of_trace(trace, reference, z) / 60.0


def hold_for(
    reading: Temperature,
    target: float,
    reference: float = REFERENCE_C,
    z: float = Z_VALUE,
) -> Duration:
    """How long ``reading`` has to be held for an F0 of ``target`` minutes."""
    return lethality.hold_for(reading, target * 60.0, reference, z)


def log_reduction(f0_minutes: float, d_value: float = STEAROTHERMOPHILUS_D121) -> float:
    """How many powers of ten the spore population came down by."""
    if d_value <= 0:
        raise ValidationError("a D value is a positive number of minutes", d_value=d_value)
    if f0_minutes < 0:
        raise ValidationError("F0 cannot be negative", f0=f0_minutes)
    return f0_minutes / d_value


def survival_level(
    population_log: float,
    f0_minutes: float,
    d_value: float = STEAROTHERMOPHILUS_D121,
) -> float:
    """The log of the expected survivors, which is the sterility assurance level.

    A population of a million spores is a log of six. Ten log reductions on top
    of that leaves a log of minus four, which is one chance in ten thousand of
    a survivor.
    """
    return population_log - log_reduction(f0_minutes, d_value)


def f0_for_sterility(
    population_log: float,
    target_level: float = -6.0,
    d_value: float = STEAROTHERMOPHILUS_D121,
) -> float:
    """F0 needed to take ``population_log`` down to ``target_level``."""
    if target_level >= population_log:
        raise ValidationError(
            "the target is not below the starting population",
            population_log=population_log,
            target_level=target_level,
        )
    return (population_log - target_level) * d_value


@dataclass(frozen=True)
class F0Result:
    """An F0 measurement judged against the floor that applied."""

    minutes: float
    floor: float
    peak: Temperature
    time_above_reference: Duration

    @property
    def reading(self) -> Reading:
        return Band.at_least(self.floor, label="F0").evaluate(self.minutes)

    @property
    def passed(self) -> bool:
        return self.reading.passed

    @property
    def shortfall(self) -> float:
        return max(self.floor - self.minutes, 0.0)

    def log_reductions(self, d_value: float = STEAROTHERMOPHILUS_D121) -> float:
        return log_reduction(self.minutes, d_value)

    def explain(self) -> str:
        if self.passed:
            return (
                f"F0 {self.minutes:.1f} min clears the floor of {self.floor:.1f}, "
                f"{self.log_reductions():.1f} log reductions"
            )
        return (
            f"F0 {self.minutes:.1f} min is {self.shortfall:.1f} short of "
            f"{self.floor:.1f}, peak {self.peak.format()}"
        )

    def __str__(self) -> str:
        return self.explain()


def evaluate(trace: Trace, floor: float = TERMINAL_FLOOR_MINUTES) -> F0Result:
    """Score a sterilizer trace against an F0 floor in minutes."""
    if floor <= 0:
        raise ValidationError("an F0 floor is a positive number", floor=floor)
    return F0Result(
        minutes=f0_of_trace(trace),
        floor=floor,
        peak=trace.peak(),
        time_above_reference=trace.time_above(Temperature(REFERENCE_C)),
    )


def equivalent_temperature(held: Duration, f0_minutes: float) -> Temperature:
    """The flat temperature that would deliver ``f0_minutes`` in ``held``."""
    return lethality.flat_temperature(held, f0_minutes * 60.0, REFERENCE_C, Z_VALUE)
