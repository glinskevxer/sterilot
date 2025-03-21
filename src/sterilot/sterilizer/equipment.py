"""Sterilizers, and the conditions under which one is allowed to run.

A sterilizer is not simply available or unavailable. It runs some methods and
not others, it needs a daily air removal test if it pulls a vacuum, and after
any repair that could affect what it does to a load it owes three consecutive
qualification runs before it may carry product again. That last rule is the one
people try to shorten when the schedule is bad, so it is a number in the
record rather than a conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import equipment_id
from sterilot.interval import DateRange
from sterilot.methods import Method

QUALIFICATION_RUNS_AFTER_REPAIR = 3


class ChamberSize(Enum):
    """Roughly how much the chamber holds, which decides load limits."""

    TABLETOP = "tabletop"
    SINGLE = "single"
    DOUBLE = "double"

    @property
    def sterilizer_units(self) -> int:
        """Capacity in the department's own unit, one basket wide by one deep."""
        return {"tabletop": 1, "single": 6, "double": 12}[self.value]

    @classmethod
    def named(cls, value: str) -> ChamberSize:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such chamber size", value=value)


@dataclass(frozen=True)
class Sterilizer:
    """One chamber and everything that decides whether it may run."""

    equipment: str
    model: str
    manufacturer: str
    methods: frozenset[Method]
    chamber: ChamberSize = ChamberSize.SINGLE
    installed_on: date | None = None
    in_service: DateRange | None = None
    out_of_order: bool = False
    qualification_runs_owed: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        if not self.model.strip():
            raise ValidationError("a sterilizer needs a model", equipment=self.equipment)
        if not self.manufacturer.strip():
            raise ValidationError("a sterilizer needs a manufacturer", equipment=self.equipment)
        if not self.methods:
            raise ValidationError("a sterilizer runs at least one method", equipment=self.equipment)
        if self.qualification_runs_owed < 0:
            raise ValidationError(
                "qualification runs owed cannot be negative", equipment=self.equipment
            )
        steam = {method for method in self.methods if method.is_steam}
        low = {method for method in self.methods if method.is_low_temperature}
        if steam and low:
            raise ValidationError(
                "no chamber runs both steam and a low temperature method",
                equipment=self.equipment,
            )

    @property
    def is_steam(self) -> bool:
        return any(method.is_steam for method in self.methods)

    @property
    def pulls_vacuum(self) -> bool:
        """Dynamic air removal and both low temperature methods evacuate."""
        return Method.STEAM_GRAVITY not in self.methods or len(self.methods) > 1

    @property
    def daily_air_removal_test(self) -> bool:
        """Only a prevacuum steam sterilizer owes a Bowie Dick each day."""
        return Method.STEAM_PREVAC in self.methods

    @property
    def capacity_units(self) -> int:
        return self.chamber.sterilizer_units

    def supports(self, method: Method) -> bool:
        return method in self.methods

    def in_service_on(self, day: date) -> bool:
        if self.in_service is None:
            return True
        return self.in_service.contains(day)

    def refusal_on(self, day: date) -> str | None:
        """Why the chamber cannot carry product today, or None."""
        if self.out_of_order:
            return "the sterilizer is out of order"
        if not self.in_service_on(day):
            return "the sterilizer is not in service"
        if self.installed_on is not None and day < self.installed_on:
            return "the sterilizer was not installed yet"
        if self.qualification_runs_owed:
            owed = self.qualification_runs_owed
            return f"the sterilizer owes {owed} qualification run{'s' if owed > 1 else ''}"
        return None

    def usable_on(self, day: date) -> bool:
        return self.refusal_on(day) is None

    def refusal_for(self, method: Method, day: date) -> str | None:
        if not self.supports(method):
            return f"this chamber does not run {method.label}"
        return self.refusal_on(day)

    def repaired(self) -> Sterilizer:
        """Put the chamber back in the qualification queue."""
        return replace(self, qualification_runs_owed=QUALIFICATION_RUNS_AFTER_REPAIR)

    def qualification_run_passed(self) -> Sterilizer:
        if not self.qualification_runs_owed:
            raise ValidationError("no qualification runs are owed", equipment=self.equipment)
        return replace(self, qualification_runs_owed=self.qualification_runs_owed - 1)

    def qualification_run_failed(self) -> Sterilizer:
        """A failed run restarts the count, it does not just repeat one."""
        return replace(self, qualification_runs_owed=QUALIFICATION_RUNS_AFTER_REPAIR)

    def label(self) -> str:
        return f"{self.equipment} {self.model}"

    def __str__(self) -> str:
        return self.label()
