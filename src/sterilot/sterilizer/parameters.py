"""Cycle specifications, and judging a run against one.

Every chamber prints a strip with a handful of numbers on it, and releasing a
load starts with somebody deciding those numbers were acceptable. Writing the
specification down as bands rather than as a sentence in a binder means that
decision is the same at three in the morning as it is at ten.

Superheat is in here rather than in the steam module because it is only
meaningful against a cycle: a chamber four degrees above its own saturation
temperature is fine on a spec that allows it and a failure on one that does
not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sterilot.errors import ValidationError
from sterilot.ids import normalise_code
from sterilot.methods import Method
from sterilot.tolerance import Band, Reading
from sterilot.units.duration import Duration
from sterilot.units.pressure import Pressure, superheat
from sterilot.units.temperature import Temperature

MINIMUM_CONDITIONING_PULSES = 3
DEFAULT_SUPERHEAT_LIMIT = 3.0


@dataclass(frozen=True)
class CycleMeasurements:
    """What the printer said the chamber did."""

    hold_temperature: Temperature
    exposure: Duration
    dry_time: Duration = field(default_factory=Duration.zero)
    chamber_pressure: Pressure | None = None
    conditioning_pulses: int | None = None

    def __post_init__(self) -> None:
        if self.conditioning_pulses is not None and self.conditioning_pulses < 0:
            raise ValidationError("pulses cannot be negative", pulses=self.conditioning_pulses)


@dataclass(frozen=True)
class CycleSpec:
    """One named cycle as the department runs it."""

    name: str
    method: Method
    temperature: Band
    exposure: Duration
    dry_time: Duration = field(default_factory=Duration.zero)
    superheat_limit: float | None = DEFAULT_SUPERHEAT_LIMIT
    conditioning_pulses: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalise_code(self.name, field="cycle name"))
        if self.exposure.seconds <= 0:
            raise ValidationError("a cycle has an exposure", name=self.name)
        if self.temperature.low is None:
            raise ValidationError("a cycle temperature band needs a floor", name=self.name)
        if not self.method.is_steam and self.superheat_limit is not None:
            raise ValidationError(
                "superheat only means something in a steam chamber", name=self.name
            )
        if self.conditioning_pulses is not None and self.method is not Method.STEAM_PREVAC:
            raise ValidationError(
                "only a prevacuum cycle counts conditioning pulses", name=self.name
            )
        if self.method is Method.STEAM_IUSS and self.dry_time.seconds > 0:
            raise ValidationError("an immediate use cycle has no dry time", name=self.name)

    @classmethod
    def standard(cls, method: Method) -> CycleSpec:
        """The department's own cycle for a method."""
        if method is Method.STEAM_PREVAC:
            return cls(
                "prevac 132",
                method,
                Band.between(132.0, 135.0, label="chamber"),
                Duration.of_minutes(4),
                Duration.of_minutes(30),
                conditioning_pulses=MINIMUM_CONDITIONING_PULSES,
            )
        if method is Method.STEAM_GRAVITY:
            return cls(
                "gravity 121",
                method,
                Band.between(121.0, 124.0, label="chamber"),
                Duration.of_minutes(30),
                Duration.of_minutes(30),
            )
        if method is Method.STEAM_IUSS:
            return cls(
                "iuss 132",
                method,
                Band.between(132.0, 135.0, label="chamber"),
                Duration.of_minutes(4),
            )
        if method is Method.HYDROGEN_PEROXIDE:
            return cls(
                "vh2o2 standard",
                method,
                Band.between(45.0, 55.0, label="chamber"),
                Duration.of_minutes(28),
                superheat_limit=None,
            )
        return cls(
            "eo 55",
            method,
            Band.between(52.0, 58.0, label="chamber"),
            Duration.of_hours(1),
            superheat_limit=None,
        )

    def readings(self, measured: CycleMeasurements) -> tuple[Reading, ...]:
        """Every parameter judged, in the order a printout lists them."""
        found: list[Reading] = [
            self.temperature.evaluate(measured.hold_temperature.celsius),
            Band.at_least(self.exposure.seconds, label="exposure").evaluate(
                measured.exposure.seconds
            ),
        ]
        if self.dry_time.seconds > 0:
            found.append(
                Band.at_least(self.dry_time.seconds, label="dry time").evaluate(
                    measured.dry_time.seconds
                )
            )
        if self.conditioning_pulses is not None:
            pulses = measured.conditioning_pulses
            found.append(
                Band.at_least(float(self.conditioning_pulses), label="pulses").evaluate(
                    float(pulses if pulses is not None else 0)
                )
            )
        if self.superheat_limit is not None and measured.chamber_pressure is not None:
            found.append(
                Band.at_most(self.superheat_limit, label="superheat").evaluate(
                    superheat(measured.hold_temperature, measured.chamber_pressure)
                )
            )
        return tuple(found)

    def failures(self, measured: CycleMeasurements) -> tuple[str, ...]:
        found = [
            reading.explain(unit=_unit_for(reading.band.label))
            for reading in self.readings(measured)
            if not reading.passed
        ]
        if (
            self.superheat_limit is not None
            and measured.chamber_pressure is None
            and self.method.is_steam
        ):
            found.append("no chamber pressure, so superheat cannot be ruled out")
        return tuple(found)

    def accepts(self, measured: CycleMeasurements) -> bool:
        return not self.failures(measured)


def _unit_for(label: str) -> str:
    return {"chamber": "C", "exposure": "s", "dry time": "s", "superheat": "C", "pulses": ""}.get(
        label, ""
    )
