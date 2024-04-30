"""Washer disinfectors and the other machines on the dirty side.

Not all of them disinfect. An ultrasonic cleaner removes soil from box locks
and lumens and does nothing to the bioburden, and a cart washer moves a lot of
water at things that are not instruments. Both are useful and neither one may
be the last machine an instrument sees before the assembly bench, which is the
rule this module exists to hold.

Qualification is the other half. A washer is qualified when it was installed
and after any repair that could change how it cleans, and a machine past its
qualification date is not a machine whose cycles mean anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import equipment_id
from sterilot.interval import DateRange

QUALIFICATION_INTERVAL_DAYS = 365


class WasherClass(Enum):
    """What kind of machine it is, which decides what it is allowed to finish."""

    SINGLE_CHAMBER = "single_chamber"
    TUNNEL = "tunnel"
    CART_WASHER = "cart_washer"
    ULTRASONIC = "ultrasonic"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def disinfects(self) -> bool:
        """Only the chamber machines run a thermal rinse."""
        return self in {WasherClass.SINGLE_CHAMBER, WasherClass.TUNNEL}

    @property
    def takes_instruments(self) -> bool:
        return self is not WasherClass.CART_WASHER

    @classmethod
    def named(cls, value: str) -> WasherClass:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such washer class", value=value)


@dataclass(frozen=True)
class Washer:
    """One machine on the dirty side."""

    equipment: str
    model: str
    manufacturer: str
    washer_class: WasherClass = WasherClass.SINGLE_CHAMBER
    chambers: int = 1
    in_service: DateRange | None = None
    last_qualification: date | None = None
    out_of_order: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        if not self.model.strip():
            raise ValidationError("a washer needs a model", equipment=self.equipment)
        if not self.manufacturer.strip():
            raise ValidationError("a washer needs a manufacturer", equipment=self.equipment)
        if self.chambers < 1:
            raise ValidationError("a washer has at least one chamber", equipment=self.equipment)
        if self.chambers > 1 and self.washer_class is not WasherClass.TUNNEL:
            raise ValidationError(
                "only a tunnel washer has more than one chamber", equipment=self.equipment
            )

    @property
    def disinfects(self) -> bool:
        return self.washer_class.disinfects

    def in_service_on(self, day: date) -> bool:
        if self.in_service is None:
            return True
        return self.in_service.contains(day)

    def qualification_due(self, day: date) -> bool:
        if self.last_qualification is None:
            return True
        return (day - self.last_qualification).days >= QUALIFICATION_INTERVAL_DAYS

    def days_to_qualification(self, day: date) -> int | None:
        if self.last_qualification is None:
            return None
        due = self.last_qualification.toordinal() + QUALIFICATION_INTERVAL_DAYS
        return due - day.toordinal()

    def refusal_on(self, day: date) -> str | None:
        """Why this machine cannot run today, or None."""
        if self.out_of_order:
            return "the machine is out of order"
        if not self.in_service_on(day):
            return "the machine is not in service"
        if self.qualification_due(day):
            return "the machine is past its qualification date"
        return None

    def usable_on(self, day: date) -> bool:
        return self.refusal_on(day) is None

    def may_finish_instruments(self, day: date) -> str | None:
        """Why this machine may not be the last one before assembly, or None."""
        refusal = self.refusal_on(day)
        if refusal is not None:
            return refusal
        if not self.washer_class.takes_instruments:
            return "a cart washer does not process instruments"
        if not self.disinfects:
            return "the machine does not run a thermal rinse"
        return None

    def qualified(self, day: date) -> Washer:
        return Washer(
            self.equipment,
            self.model,
            self.manufacturer,
            self.washer_class,
            self.chambers,
            self.in_service,
            day,
            self.out_of_order,
        )

    def label(self) -> str:
        return f"{self.equipment} {self.model}"

    def __str__(self) -> str:
        return self.label()
