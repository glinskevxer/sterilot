"""Tolerance bands, and what it means to be outside one.

A cycle parameter is never just a number. It is a number against a band, and
the interesting part of a failed cycle is not that it failed but by how much
and on which side. A chamber two tenths of a degree under its floor and a
chamber eleven degrees under its floor are the same boolean and very different
conversations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sterilot.errors import ValidationError


class Side(Enum):
    """Where a reading sits relative to its band."""

    INSIDE = "inside"
    BELOW = "below"
    ABOVE = "above"

    @property
    def is_failure(self) -> bool:
        return self is not Side.INSIDE


@dataclass(frozen=True)
class Band:
    """An inclusive band. Either bound may be absent, but not both."""

    low: float | None = None
    high: float | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if self.low is None and self.high is None:
            raise ValidationError("a band needs at least one bound")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValidationError(
                "band bounds are the wrong way round", low=self.low, high=self.high
            )

    @classmethod
    def at_least(cls, low: float, label: str = "") -> Band:
        return cls(low=low, label=label)

    @classmethod
    def at_most(cls, high: float, label: str = "") -> Band:
        return cls(high=high, label=label)

    @classmethod
    def between(cls, low: float, high: float, label: str = "") -> Band:
        return cls(low=low, high=high, label=label)

    @classmethod
    def around(
        cls, nominal: float, minus: float, plus: float | None = None, label: str = ""
    ) -> Band:
        """A band written the way a spec sheet writes it, nominal plus or minus."""
        if minus < 0:
            raise ValidationError("the minus side of a band is a magnitude", minus=minus)
        upper = minus if plus is None else plus
        if upper < 0:
            raise ValidationError("the plus side of a band is a magnitude", plus=upper)
        return cls(low=nominal - minus, high=nominal + upper, label=label)

    def side(self, value: float) -> Side:
        if self.low is not None and value < self.low:
            return Side.BELOW
        if self.high is not None and value > self.high:
            return Side.ABOVE
        return Side.INSIDE

    def contains(self, value: float) -> bool:
        return self.side(value) is Side.INSIDE

    def deviation(self, value: float) -> float:
        """Signed distance outside the band. Zero when the value is inside."""
        side = self.side(value)
        if side is Side.BELOW and self.low is not None:
            return value - self.low
        if side is Side.ABOVE and self.high is not None:
            return value - self.high
        return 0.0

    def evaluate(self, value: float) -> Reading:
        return Reading(value=value, band=self, side=self.side(value))

    def widened_by(self, amount: float) -> Band:
        if amount < 0:
            raise ValidationError("cannot widen a band by a negative amount", amount=amount)
        return Band(
            low=None if self.low is None else self.low - amount,
            high=None if self.high is None else self.high + amount,
            label=self.label,
        )

    def format(self, places: int = 1, unit: str = "") -> str:
        suffix = f" {unit}" if unit else ""
        if self.low is not None and self.high is not None:
            return f"{self.low:.{places}f} to {self.high:.{places}f}{suffix}"
        if self.low is not None:
            return f"at least {self.low:.{places}f}{suffix}"
        return f"no more than {self.high:.{places}f}{suffix}"

    def __str__(self) -> str:
        return self.format()


@dataclass(frozen=True)
class Reading:
    """A value judged against a band, kept together so a report can say why."""

    value: float
    band: Band
    side: Side

    @property
    def passed(self) -> bool:
        return self.side is Side.INSIDE

    @property
    def deviation(self) -> float:
        return self.band.deviation(self.value)

    def explain(self, places: int = 1, unit: str = "") -> str:
        name = self.band.label or "value"
        suffix = f" {unit}" if unit else ""
        if self.passed:
            return (
                f"{name} {self.value:.{places}f}{suffix} is inside {self.band.format(places, unit)}"
            )
        direction = "under" if self.side is Side.BELOW else "over"
        gap = abs(self.deviation)
        return (
            f"{name} {self.value:.{places}f}{suffix} is {gap:.{places}f}{suffix} "
            f"{direction} {self.band.format(places, unit)}"
        )

    def __str__(self) -> str:
        return self.explain()
