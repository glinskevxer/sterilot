"""The sterilization methods the department runs, and what each one costs you.

Method is not a label on a cycle record. It decides what may go in the load,
what the parameters mean, how long the item is unavailable afterwards, and
whether the packaging is allowed anywhere near it. Cellulose in a hydrogen
peroxide chamber aborts the cycle, and an ethylene oxide load is out of service
for half a day in aeration whether anyone remembered that or not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


class Method(Enum):
    """A sterilization method as the department schedules it."""

    STEAM_PREVAC = "steam_prevac"
    STEAM_GRAVITY = "steam_gravity"
    STEAM_IUSS = "steam_iuss"
    HYDROGEN_PEROXIDE = "hydrogen_peroxide"
    ETHYLENE_OXIDE = "ethylene_oxide"

    @classmethod
    def named(cls, value: str) -> Method:
        wanted = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "prevac": cls.STEAM_PREVAC,
            "pre_vacuum": cls.STEAM_PREVAC,
            "dynamic_air_removal": cls.STEAM_PREVAC,
            "gravity": cls.STEAM_GRAVITY,
            "iuss": cls.STEAM_IUSS,
            "flash": cls.STEAM_IUSS,
            "vh2o2": cls.HYDROGEN_PEROXIDE,
            "peroxide": cls.HYDROGEN_PEROXIDE,
            "eo": cls.ETHYLENE_OXIDE,
            "eto": cls.ETHYLENE_OXIDE,
        }
        for method in cls:
            if wanted == method.value:
                return method
        if wanted in aliases:
            return aliases[wanted]
        raise ValidationError("no such sterilization method", value=value)

    @property
    def label(self) -> str:
        return {
            "steam_prevac": "steam, dynamic air removal",
            "steam_gravity": "steam, gravity displacement",
            "steam_iuss": "steam, immediate use",
            "hydrogen_peroxide": "vaporized hydrogen peroxide",
            "ethylene_oxide": "ethylene oxide",
        }[self.value]

    @property
    def is_steam(self) -> bool:
        return self.value.startswith("steam")

    @property
    def is_low_temperature(self) -> bool:
        return not self.is_steam

    @property
    def tolerates_cellulose(self) -> bool:
        """Paper, muslin and cotton absorb peroxide and abort the cycle."""
        return self is not Method.HYDROGEN_PEROXIDE

    @property
    def tolerates_moisture(self) -> bool:
        """Both low temperature methods need the load bone dry going in."""
        return self.is_steam

    @property
    def aeration(self) -> Duration:
        """Time the load is unavailable after the cycle, before it can be used."""
        if self is Method.ETHYLENE_OXIDE:
            return Duration.of_hours(12)
        return Duration.zero()

    @property
    def may_be_stored(self) -> bool:
        """Immediate use loads go straight to the room, never to a shelf."""
        return self is not Method.STEAM_IUSS

    @property
    def nominal_temperature(self) -> Temperature:
        return {
            "steam_prevac": Temperature(132.0),
            "steam_gravity": Temperature(121.0),
            "steam_iuss": Temperature(132.0),
            "hydrogen_peroxide": Temperature(50.0),
            "ethylene_oxide": Temperature(55.0),
        }[self.value]

    @property
    def nominal_exposure(self) -> Duration:
        return {
            "steam_prevac": Duration.of_minutes(4),
            "steam_gravity": Duration.of_minutes(30),
            "steam_iuss": Duration.of_minutes(4),
            "hydrogen_peroxide": Duration.of_minutes(28),
            "ethylene_oxide": Duration.of_hours(1),
        }[self.value]

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True)
class MethodProfile:
    """A method as one department runs it, which is not always the nominal."""

    method: Method
    temperature: Temperature
    exposure: Duration
    dry_time: Duration = field(default_factory=Duration.zero)

    def __post_init__(self) -> None:
        if self.exposure.seconds <= 0:
            raise ValidationError("exposure must be longer than nothing", method=self.method.value)
        if self.method.is_steam and self.temperature.celsius < 100.0:
            raise ValidationError(
                "a steam cycle below boiling is not a steam cycle",
                celsius=self.temperature.celsius,
            )
        if self.method is Method.STEAM_IUSS and self.dry_time.seconds > 0:
            raise ValidationError("immediate use cycles have no dry time")

    @classmethod
    def nominal(cls, method: Method) -> MethodProfile:
        dry = (
            Duration.of_minutes(30) if method.is_steam and method.may_be_stored else Duration.zero()
        )
        return cls(method, method.nominal_temperature, method.nominal_exposure, dry)

    @property
    def total_cycle(self) -> Duration:
        return self.exposure + self.dry_time

    @property
    def unavailable_for(self) -> Duration:
        return self.total_cycle + self.method.aeration

    def describe(self) -> str:
        return f"{self.method.label} at {self.temperature.format()} for {self.exposure.spelled()}"
