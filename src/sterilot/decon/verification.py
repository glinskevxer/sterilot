"""Cleaning verification, which is the only evidence the washer works.

An A0 value says the load got hot. It does not say the load got clean, and a
soiled instrument that has been thermally disinfected is still a soiled
instrument. So the department runs a soil test device through each washer every
day it is used, and samples instruments off the assembly bench with a protein
or ATP test.

A failed verification is not a single bad result. It calls into question every
cycle that machine ran since the last passing test, which is why the log knows
how to look backwards.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number, equipment_id, indicator_lot
from sterilot.tolerance import Band


class VerificationKind(Enum):
    """The verification tests the department runs."""

    SOIL_DEVICE = "soil_device"
    PROTEIN = "protein"
    ATP = "atp"
    HAEMOGLOBIN = "haemoglobin"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def is_visual(self) -> bool:
        """A soil device is read by eye, so it has no number."""
        return self is VerificationKind.SOIL_DEVICE

    @property
    def unit(self) -> str:
        return {"soil_device": "", "protein": "ug", "atp": "RLU", "haemoglobin": "ug"}[self.value]

    @property
    def limit(self) -> Band | None:
        """The department's acceptance band, or None for a visual test."""
        if self is VerificationKind.PROTEIN:
            return Band.at_most(3.0, label="protein")
        if self is VerificationKind.ATP:
            return Band.at_most(100.0, label="ATP")
        if self is VerificationKind.HAEMOGLOBIN:
            return Band.at_most(0.1, label="haemoglobin")
        return None

    @classmethod
    def named(cls, value: str) -> VerificationKind:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such verification check", value=value)


@dataclass(frozen=True)
class Verification:
    """One verification result."""

    kind: VerificationKind
    equipment: str
    at: datetime
    by: str
    value: float | None = None
    visual_pass: bool | None = None
    lot: str = ""
    subject: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        object.__setattr__(self, "by", badge_number(self.by))
        if self.lot:
            object.__setattr__(self, "lot", indicator_lot(self.lot))
        if self.kind.is_visual:
            if self.visual_pass is None:
                raise ValidationError("a visual test needs a reading", kind=self.kind.value)
            if self.value is not None:
                raise ValidationError("a visual test has no number", kind=self.kind.value)
        else:
            if self.value is None:
                raise ValidationError("a measured test needs a value", kind=self.kind.value)
            if self.value < 0:
                raise ValidationError("a residue reading cannot be negative", value=self.value)
            if self.visual_pass is not None:
                raise ValidationError("a measured test is not read by eye", kind=self.kind.value)

    @property
    def day(self) -> date:
        return self.at.date()

    @property
    def passed(self) -> bool:
        if self.kind.is_visual:
            return bool(self.visual_pass)
        limit = self.kind.limit
        assert limit is not None
        assert self.value is not None
        return limit.contains(self.value)

    def explain(self) -> str:
        where = f" on {self.subject}" if self.subject else ""
        if self.kind.is_visual:
            verdict = "passed" if self.passed else "failed"
            return f"{self.kind.label} {verdict} on {self.equipment}{where}"
        limit = self.kind.limit
        assert limit is not None
        assert self.value is not None
        return f"{self.equipment}{where}: {limit.evaluate(self.value).explain(unit=self.kind.unit)}"

    def __str__(self) -> str:
        return self.explain()


@dataclass(frozen=True)
class VerificationLog:
    """Every verification result, for looking backwards after a failure."""

    results: tuple[Verification, ...] = ()

    @classmethod
    def of(cls, results: Iterable[Verification]) -> VerificationLog:
        return cls(tuple(sorted(results, key=lambda item: item.at)))

    def with_result(self, result: Verification) -> VerificationLog:
        return VerificationLog.of((*self.results, result))

    def for_equipment(self, equipment: str) -> tuple[Verification, ...]:
        wanted = equipment_id(equipment)
        return tuple(item for item in self.results if item.equipment == wanted)

    def on_day(self, equipment: str, day: date) -> tuple[Verification, ...]:
        return tuple(item for item in self.for_equipment(equipment) if item.day == day)

    def verified_on(self, equipment: str, day: date) -> bool:
        """A soil device test ran that day and passed."""
        return any(
            item.kind is VerificationKind.SOIL_DEVICE and item.passed
            for item in self.on_day(equipment, day)
        )

    def last_pass_before(self, equipment: str, moment: datetime) -> Verification | None:
        found: Verification | None = None
        for item in self.for_equipment(equipment):
            if item.at <= moment and item.passed and item.kind is VerificationKind.SOIL_DEVICE:
                found = item
        return found

    def suspect_window(self, equipment: str, failure: Verification) -> tuple[datetime, datetime]:
        """The window a failed test calls into question.

        From the last passing soil device test on that machine up to the
        failure. With no earlier pass the window opens at the first result the
        log holds, because that is as far back as the evidence goes.
        """
        if failure.passed:
            raise ValidationError("that test did not fail", equipment=failure.equipment)
        previous = self.last_pass_before(equipment, failure.at)
        if previous is not None:
            return previous.at, failure.at
        earlier = self.for_equipment(equipment)
        start = earlier[0].at if earlier else failure.at
        return start, failure.at
