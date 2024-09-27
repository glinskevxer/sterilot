"""Attrition: instruments quietly disappearing, and what to buy because of it.

Instruments leave a set three ways. They break, they get thrown out with the
drapes, and they walk off in somebody's pocket. Only the first one generates a
repair order, so a department that watches only the repair bench sees maybe
half of what it is losing.

The number that matters is the rate per set per year, because that is what
turns into a purchase order. A set losing four percent of its pieces a year and
a set losing forty are the same complaint at the assembly bench and very
different budget lines.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import catalog_number, tray_code


class Loss(Enum):
    """Why an instrument left the set."""

    BROKEN = "broken"
    WORN = "worn"
    MISSING = "missing"
    CONTAMINATED = "contaminated"

    @property
    def label(self) -> str:
        return self.value

    @property
    def repairable(self) -> bool:
        """Only a broken or worn instrument is worth sending to a vendor."""
        return self in {Loss.BROKEN, Loss.WORN}

    @classmethod
    def named(cls, value: str) -> Loss:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such loss reason", value=value)


@dataclass(frozen=True)
class Period:
    """One catalog number in one set over one year."""

    year: int
    code: str
    catalog: str
    opening: int
    losses: dict[Loss, int]
    purchased: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", tray_code(self.code))
        object.__setattr__(self, "catalog", catalog_number(self.catalog))
        if self.opening < 0 or self.purchased < 0:
            raise ValidationError("counts cannot be negative", catalog=self.catalog)
        if any(count < 0 for count in self.losses.values()):
            raise ValidationError("a loss count cannot be negative", catalog=self.catalog)
        if self.lost > self.opening + self.purchased:
            raise ValidationError(
                "more went missing than the department ever had", catalog=self.catalog
            )

    @property
    def lost(self) -> int:
        return sum(self.losses.values())

    @property
    def closing(self) -> int:
        return self.opening + self.purchased - self.lost

    @property
    def rate(self) -> float:
        """Losses as a share of what was there at the start of the year."""
        if self.opening == 0:
            return 0.0
        return self.lost / self.opening

    def losses_of(self, reason: Loss) -> int:
        return self.losses.get(reason, 0)

    @property
    def repairable(self) -> int:
        return sum(count for reason, count in self.losses.items() if reason.repairable)

    def describe(self) -> str:
        return (
            f"{self.year} {self.code} {self.catalog}: {self.opening} opening, "
            f"{self.lost} lost, {self.closing} closing"
        )


@dataclass(frozen=True)
class AttritionTable:
    """Several years of periods, which is what a forecast needs."""

    periods: tuple[Period, ...] = ()

    @classmethod
    def of(cls, periods: Iterable[Period]) -> AttritionTable:
        return cls(tuple(sorted(periods, key=lambda item: (item.code, item.catalog, item.year))))

    def for_item(self, code: str, catalog: str) -> tuple[Period, ...]:
        wanted_code = tray_code(code)
        wanted_catalog = catalog_number(catalog)
        return tuple(
            item
            for item in self.periods
            if item.code == wanted_code and item.catalog == wanted_catalog
        )

    def rate_for(self, code: str, catalog: str) -> float:
        """Average yearly loss rate, weighted by how much was in service."""
        found = self.for_item(code, catalog)
        opening = sum(item.opening for item in found)
        if opening == 0:
            return 0.0
        return sum(item.lost for item in found) / opening

    def forecast(self, code: str, catalog: str, on_hand: int, years: float = 1.0) -> int:
        """How many to buy to hold ``on_hand`` steady over ``years``."""
        if on_hand < 0:
            raise ValidationError("a count cannot be negative", catalog=catalog)
        if years <= 0:
            raise ValidationError("a forecast covers time", years=years)
        expected = self.rate_for(code, catalog) * on_hand * years
        whole = int(expected)
        return whole + 1 if expected > whole else whole

    def worst(self, limit: int = 5) -> tuple[tuple[str, str, float], ...]:
        """The set and catalog pairs losing the most, worst first."""
        if limit < 1:
            raise ValidationError("a list has at least one line", limit=limit)
        pairs = {(item.code, item.catalog) for item in self.periods}
        scored = [(code, catalog, self.rate_for(code, catalog)) for code, catalog in pairs]
        scored.sort(key=lambda row: (-row[2], row[0], row[1]))
        return tuple(scored[:limit])
