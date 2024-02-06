"""Mass, because a set that is too heavy will not dry.

The weight limit on a wrapped or containerised set is not a handling rule, or
not only one. A heavy set holds enough metal to condense more steam than the
dry stage can drive back off, and it comes out of the chamber wet. A wet pack
is not sterile. So the assembly bench weighs sets, and the limit is a real
gate, not advice.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sterilot.errors import ValidationError

GRAMS_PER_POUND = 453.59237
GRAMS_PER_OUNCE = 28.349523125

SET_WEIGHT_LIMIT_KG = 11.4
"""The department limit on a complete set, container and contents together."""

_PATTERN = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|lb|lbs|oz)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class Mass:
    """A mass in kilograms. Never negative."""

    kilograms: float

    def __post_init__(self) -> None:
        if self.kilograms < 0:
            raise ValidationError("mass cannot be negative", kilograms=self.kilograms)

    @classmethod
    def of_kilograms(cls, value: float) -> Mass:
        return cls(float(value))

    @classmethod
    def of_grams(cls, value: float) -> Mass:
        return cls(float(value) / 1000.0)

    @classmethod
    def of_pounds(cls, value: float) -> Mass:
        return cls(float(value) * GRAMS_PER_POUND / 1000.0)

    @classmethod
    def of_ounces(cls, value: float) -> Mass:
        return cls(float(value) * GRAMS_PER_OUNCE / 1000.0)

    @classmethod
    def zero(cls) -> Mass:
        return cls(0.0)

    @classmethod
    def parse(cls, text: str) -> Mass:
        """Read ``10.4kg``, ``23 lb``, ``800 g`` or a bare number as kilograms."""
        match = _PATTERN.match(text)
        if match is None:
            raise ValidationError("cannot read that as a mass", text=text)
        value = float(match.group("value"))
        unit = (match.group("unit") or "kg").lower()
        if unit == "kg":
            return cls(value)
        if unit == "g":
            return cls.of_grams(value)
        if unit in {"lb", "lbs"}:
            return cls.of_pounds(value)
        return cls.of_ounces(value)

    @property
    def grams(self) -> float:
        return self.kilograms * 1000.0

    @property
    def pounds(self) -> float:
        return self.kilograms * 1000.0 / GRAMS_PER_POUND

    @property
    def ounces(self) -> float:
        return self.kilograms * 1000.0 / GRAMS_PER_OUNCE

    def __add__(self, other: Mass) -> Mass:
        return Mass(self.kilograms + other.kilograms)

    def __sub__(self, other: Mass) -> Mass:
        return Mass(self.kilograms - other.kilograms)

    def __mul__(self, factor: float) -> Mass:
        if factor < 0:
            raise ValidationError("cannot scale a mass by a negative factor", factor=factor)
        return Mass(self.kilograms * factor)

    def over(self, limit: Mass) -> Mass:
        """How far this mass exceeds ``limit``, zero when it is inside."""
        if self.kilograms <= limit.kilograms:
            return Mass.zero()
        return Mass(self.kilograms - limit.kilograms)

    def rounded(self, places: int = 2) -> Mass:
        return Mass(round(self.kilograms, places))

    def format(self, unit: str = "kg", places: int = 2) -> str:
        wanted = unit.lower()
        if wanted == "kg":
            return f"{self.kilograms:.{places}f} kg"
        if wanted == "g":
            return f"{self.grams:.{places}f} g"
        if wanted in {"lb", "lbs"}:
            return f"{self.pounds:.{places}f} lb"
        if wanted == "oz":
            return f"{self.ounces:.{places}f} oz"
        raise ValidationError("unknown mass unit", unit=unit)

    def __str__(self) -> str:
        return self.format()


def set_weight_limit() -> Mass:
    """The department limit as a :class:`Mass`."""
    return Mass(SET_WEIGHT_LIMIT_KG)


def total(masses: Iterable[Mass]) -> Mass:
    return Mass(sum(item.kilograms for item in masses))


def heaviest(masses: Iterable[Mass]) -> Mass:
    values = list(masses)
    if not values:
        raise ValidationError("no masses to take a maximum of")
    return max(values)
