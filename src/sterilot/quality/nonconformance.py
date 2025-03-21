"""Nonconformances: the department writing down what went wrong.

The point of the register is not blame, it is that the same thing happening
eleven times is a different problem from it happening once. A single wet pack
is a bad load. Eleven wet packs on the same chamber in a month is a steam
supply problem and somebody has to call engineering.

Severity decides how fast a response is owed and whether an investigation is
required at all. A critical finding is one where something unsterile reached a
patient or could have, and those never close on the same day they open.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import badge_number, normalise_code


class Severity(Enum):
    """How bad it was."""

    OBSERVATION = "observation"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"

    @property
    def label(self) -> str:
        return self.value

    @property
    def response_days(self) -> int:
        return {"observation": 30, "minor": 14, "major": 5, "critical": 1}[self.value]

    @property
    def needs_investigation(self) -> bool:
        return self in {Severity.MAJOR, Severity.CRITICAL}

    @classmethod
    def named(cls, value: str) -> Severity:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such severity", value=value)


class Category(Enum):
    """Which part of the department it came from."""

    POINT_OF_USE = "point_of_use"
    CLEANING = "cleaning"
    ASSEMBLY = "assembly"
    STERILIZATION = "sterilization"
    STORAGE = "storage"
    TRANSPORT = "transport"
    LOANER = "loaner"
    DOCUMENTATION = "documentation"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def named(cls, value: str) -> Category:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such category", value=value)


@dataclass(frozen=True)
class Nonconformance:
    """One thing that went wrong."""

    reference: str
    category: Category
    severity: Severity
    raised_at: datetime
    raised_by: str
    description: str
    subject: str = ""
    immediate_action: str = ""
    investigation: str = ""
    closed_at: datetime | None = None
    closed_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="exception reference")
        )
        object.__setattr__(self, "raised_by", badge_number(self.raised_by))
        if self.closed_by:
            object.__setattr__(self, "closed_by", badge_number(self.closed_by))
        if not self.description.strip():
            raise ValidationError("an exception says what happened", reference=self.reference)
        if self.closed_at is not None:
            if self.closed_at < self.raised_at:
                raise ValidationError(
                    "an exception cannot close before it opens", reference=self.reference
                )
            if not self.closed_by:
                raise ValidationError("a closed exception is signed", reference=self.reference)
            if self.severity.needs_investigation and not self.investigation.strip():
                raise ValidationError(
                    "a major or critical finding closes with an investigation",
                    reference=self.reference,
                )
            if (
                self.severity is Severity.CRITICAL
                and self.closed_at.date() == self.raised_at.date()
            ):
                raise ValidationError(
                    "a critical finding does not close the day it opened",
                    reference=self.reference,
                )

    @property
    def open(self) -> bool:
        return self.closed_at is None

    def due_on(self) -> date:
        return date.fromordinal(self.raised_at.date().toordinal() + self.severity.response_days)

    def overdue(self, now: date) -> bool:
        return self.open and now > self.due_on()

    def age_days(self, now: date) -> int:
        end = self.closed_at.date() if self.closed_at is not None else now
        return (end - self.raised_at.date()).days

    def closed(self, at: datetime, by: str, investigation: str = "") -> Nonconformance:
        if not self.open:
            raise ConflictError("that exception is already closed", reference=self.reference)
        return replace(
            self,
            investigation=investigation or self.investigation,
            closed_at=at,
            closed_by=by,
        )

    def summary(self) -> str:
        state = "open" if self.open else "closed"
        where = f" on {self.subject}" if self.subject else ""
        return f"{self.reference} {self.severity.label} {self.category.label}{where}, {state}"

    def __str__(self) -> str:
        return self.summary()


@dataclass(frozen=True)
class ExceptionRegister:
    """Every exception raised, which is where a trend shows up."""

    entries: tuple[Nonconformance, ...] = ()

    @classmethod
    def of(cls, entries: Iterable[Nonconformance]) -> ExceptionRegister:
        register = cls()
        for entry in entries:
            register = register.with_entry(entry)
        return register

    def with_entry(self, entry: Nonconformance) -> ExceptionRegister:
        if any(item.reference == entry.reference for item in self.entries):
            raise ConflictError("that exception reference is used", reference=entry.reference)
        return ExceptionRegister((*self.entries, entry))

    def replacing(self, entry: Nonconformance) -> ExceptionRegister:
        if not any(item.reference == entry.reference for item in self.entries):
            raise NotFoundError("no exception with that reference", reference=entry.reference)
        return ExceptionRegister(
            tuple(entry if item.reference == entry.reference else item for item in self.entries)
        )

    def get(self, reference: str) -> Nonconformance:
        wanted = normalise_code(reference, field="exception reference")
        for entry in self.entries:
            if entry.reference == wanted:
                return entry
        raise NotFoundError("no exception with that reference", reference=wanted)

    def open_entries(self) -> tuple[Nonconformance, ...]:
        return tuple(entry for entry in self.entries if entry.open)

    def overdue(self, now: date) -> tuple[Nonconformance, ...]:
        return tuple(entry for entry in self.entries if entry.overdue(now))

    def by_category(self) -> dict[Category, int]:
        counts: dict[Category, int] = {}
        for entry in self.entries:
            counts[entry.category] = counts.get(entry.category, 0) + 1
        return counts

    def about(self, subject: str) -> tuple[Nonconformance, ...]:
        wanted = subject.strip().upper()
        return tuple(entry for entry in self.entries if entry.subject.upper() == wanted)

    def repeat_subjects(self, threshold: int = 3) -> tuple[tuple[str, int], ...]:
        """Subjects that keep coming back, worst first."""
        if threshold < 2:
            raise ValidationError("a repeat needs at least two", threshold=threshold)
        counts: dict[str, int] = {}
        for entry in self.entries:
            if entry.subject:
                counts[entry.subject] = counts.get(entry.subject, 0) + 1
        found = [(subject, count) for subject, count in counts.items() if count >= threshold]
        return tuple(sorted(found, key=lambda row: (-row[1], row[0])))
