"""Temperature, in the one unit the department actually records.

Everything inside sterilot is Celsius. The department's steam sterilizers print
Celsius, the washers print Celsius, and the two Fahrenheit displays left in the
building are converted at the door. Keeping one internal unit means a
comparison never has to ask what it is comparing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sterilot.errors import ValidationError

ABSOLUTE_ZERO_C = -273.15
SANITY_CEILING_C = 400.0

_PATTERN = re.compile(
    r"^\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?:deg\s*)?(?P<unit>[cCfFkK])?\s*$",
)


@dataclass(frozen=True, order=True)
class Temperature:
    """A temperature reading, stored in Celsius."""

    celsius: float

    def __post_init__(self) -> None:
        if self.celsius < ABSOLUTE_ZERO_C:
            raise ValidationError("temperature is below absolute zero", celsius=self.celsius)
        if self.celsius > SANITY_CEILING_C:
            raise ValidationError(
                "temperature is far above anything this department runs",
                celsius=self.celsius,
                ceiling=SANITY_CEILING_C,
            )

    @classmethod
    def from_celsius(cls, value: float) -> Temperature:
        return cls(float(value))

    @classmethod
    def from_fahrenheit(cls, value: float) -> Temperature:
        return cls((float(value) - 32.0) * 5.0 / 9.0)

    @classmethod
    def from_kelvin(cls, value: float) -> Temperature:
        return cls(float(value) + ABSOLUTE_ZERO_C)

    @classmethod
    def parse(cls, text: str) -> Temperature:
        """Read ``134C``, ``273.2 F``, ``407.15K`` or a bare number as Celsius."""
        match = _PATTERN.match(text)
        if match is None:
            raise ValidationError("cannot read that as a temperature", text=text)
        value = float(match.group("value"))
        unit = (match.group("unit") or "C").upper()
        if unit == "F":
            return cls.from_fahrenheit(value)
        if unit == "K":
            return cls.from_kelvin(value)
        return cls(value)

    @property
    def fahrenheit(self) -> float:
        return self.celsius * 9.0 / 5.0 + 32.0

    @property
    def kelvin(self) -> float:
        return self.celsius - ABSOLUTE_ZERO_C

    def difference(self, other: Temperature) -> float:
        """Celsius degrees between this reading and ``other``, signed."""
        return self.celsius - other.celsius

    def offset_by(self, degrees: float) -> Temperature:
        """A reading ``degrees`` Celsius away from this one."""
        return Temperature(self.celsius + degrees)

    def within(self, other: Temperature, tolerance: float) -> bool:
        """True when the two readings are no further apart than ``tolerance``."""
        if tolerance < 0:
            raise ValidationError("tolerance cannot be negative", tolerance=tolerance)
        return abs(self.difference(other)) <= tolerance

    def rounded(self, places: int = 1) -> Temperature:
        return Temperature(round(self.celsius, places))

    def is_at_least(self, floor: Temperature) -> bool:
        return self.celsius >= floor.celsius

    def format(self, unit: str = "C", places: int = 1) -> str:
        """Render for a report in whichever unit the reader wants."""
        wanted = unit.upper()
        if wanted == "C":
            return f"{self.celsius:.{places}f} C"
        if wanted == "F":
            return f"{self.fahrenheit:.{places}f} F"
        if wanted == "K":
            return f"{self.kelvin:.{places}f} K"
        raise ValidationError("unknown temperature unit", unit=unit)

    def __str__(self) -> str:
        return self.format()


def hottest(readings: Iterable[Temperature]) -> Temperature:
    """The highest reading in an iterable, which must not be empty."""
    values = list(readings)
    if not values:
        raise ValidationError("no readings to take a maximum of")
    return max(values)


def coldest(readings: Iterable[Temperature]) -> Temperature:
    """The lowest reading in an iterable, which must not be empty."""
    values = list(readings)
    if not values:
        raise ValidationError("no readings to take a minimum of")
    return min(values)
