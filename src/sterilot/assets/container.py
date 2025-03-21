"""Rigid containers, and the consumables that make them work.

A container is not packaging you buy once. It is a filter that has to be
changed every cycle, a gasket that has to seal, latches that have to hold, and
a lid that has to match the base. Any one of those failing turns a sterile set
into a set that looks sterile, which is worse.

The filter is where method comes back in. Paper filters are cellulose, so a
container filtered with paper cannot go in the peroxide chamber whatever its
contents are made of.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import asset_tag
from sterilot.interval import DateRange
from sterilot.methods import Method

INSPECTION_INTERVAL_CYCLES = 60
INSPECTION_INTERVAL_DAYS = 365


class FilterType(Enum):
    """What is covering the vents."""

    PAPER = "paper"
    SYNTHETIC = "synthetic"
    VALVE = "valve"

    @property
    def is_cellulose(self) -> bool:
        return self is FilterType.PAPER

    @property
    def single_use(self) -> bool:
        """Valves are cleaned and reused. Filters are not."""
        return self is not FilterType.VALVE

    @property
    def label(self) -> str:
        return {
            "paper": "disposable paper",
            "synthetic": "disposable synthetic",
            "valve": "reusable valve",
        }[self.value]

    @classmethod
    def named(cls, value: str) -> FilterType:
        wanted = value.strip().lower()
        for member in cls:
            if wanted in {member.value, member.label}:
                return member
        raise ValidationError("no such filter type", value=value)


@dataclass(frozen=True)
class Container:
    """One rigid container, base and lid together."""

    asset: str
    model: str
    manufacturer: str
    filter_type: FilterType
    filter_positions: int = 2
    in_service: DateRange | None = None
    last_inspection: date | None = None
    cycles_since_inspection: int = 0
    gasket_intact: bool = True
    latches_intact: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        if not self.model.strip():
            raise ValidationError("a container needs a model", asset=self.asset)
        if not self.manufacturer.strip():
            raise ValidationError("a container needs a manufacturer", asset=self.asset)
        if self.filter_positions < 1:
            raise ValidationError("a container has at least one vent", asset=self.asset)
        if self.cycles_since_inspection < 0:
            raise ValidationError("cycle count cannot be negative", asset=self.asset)

    @property
    def filters_per_cycle(self) -> int:
        """Filters consumed on each run. Valve containers consume none."""
        return self.filter_positions if self.filter_type.single_use else 0

    def in_service_on(self, day: date) -> bool:
        if self.in_service is None:
            return True
        return self.in_service.contains(day)

    def inspection_due(self, day: date) -> bool:
        if self.last_inspection is None:
            return True
        if self.cycles_since_inspection >= INSPECTION_INTERVAL_CYCLES:
            return True
        return (day - self.last_inspection).days >= INSPECTION_INTERVAL_DAYS

    def refusal_for(self, method: Method, day: date) -> str | None:
        """Why this container cannot run ``method`` on ``day``, or None."""
        if not self.in_service_on(day):
            return "the container is not in service"
        if not self.gasket_intact:
            return "the gasket does not seal"
        if not self.latches_intact:
            return "a latch is damaged"
        if self.inspection_due(day):
            return "the container is due for inspection"
        if self.filter_type.is_cellulose and not method.tolerates_cellulose:
            return "paper filters are cellulose and cannot go in that chamber"
        return None

    def usable_for(self, method: Method, day: date) -> bool:
        return self.refusal_for(method, day) is None

    def methods(self, day: date) -> tuple[Method, ...]:
        return tuple(method for method in Method if self.usable_for(method, day))

    def after_cycle(self) -> Container:
        """The same container one cycle further from its inspection."""
        return replace(self, cycles_since_inspection=self.cycles_since_inspection + 1)

    def inspected(
        self, day: date, gasket_intact: bool = True, latches_intact: bool = True
    ) -> Container:
        return replace(
            self,
            last_inspection=day,
            cycles_since_inspection=0,
            gasket_intact=gasket_intact,
            latches_intact=latches_intact,
        )

    def label(self) -> str:
        return f"{self.asset} {self.model}"

    def __str__(self) -> str:
        return self.label()
