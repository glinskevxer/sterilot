"""Competencies: who has been signed off to do which job.

A role says what somebody was hired as. A competency says somebody watched them
do the task and wrote it down, which is the thing an inspector asks for. They
run out, because a technician who has not loaded a sterilizer in two years is
not the technician who was assessed on it.

Two rules that look like bureaucracy and are not. Nobody assesses themselves,
and an assessor has to hold the competency they are assessing. Otherwise the
whole record is somebody's opinion of their own work.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number
from sterilot.interval import DateRange

REASSESSMENT_INTERVAL_DAYS = 365


class Task(Enum):
    """The jobs the department assesses separately."""

    POINT_OF_USE = "point_of_use"
    MANUAL_CLEAN = "manual_clean"
    WASHER = "washer"
    ASSEMBLY = "assembly"
    STERILIZER = "sterilizer"
    RELEASE = "release"
    LOANER_INTAKE = "loaner_intake"
    RECALL = "recall"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def high_risk(self) -> bool:
        """The tasks where a mistake reaches a patient directly."""
        return self in {Task.STERILIZER, Task.RELEASE, Task.RECALL}

    @classmethod
    def named(cls, value: str) -> Task:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such task", value=value)


@dataclass(frozen=True)
class Competency:
    """One assessment of one person on one task."""

    badge: str
    task: Task
    assessed_on: date
    assessor: str
    observations: int = 1
    valid_until: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "badge", badge_number(self.badge))
        object.__setattr__(self, "assessor", badge_number(self.assessor))
        if self.badge == self.assessor:
            raise ValidationError("nobody assesses themselves", badge=self.badge)
        if self.observations < 1:
            raise ValidationError("an assessment observes the work at least once", badge=self.badge)
        if self.task.high_risk and self.observations < 3:
            raise ValidationError(
                "a high risk task is observed three times",
                badge=self.badge,
                task=self.task.value,
            )
        if self.valid_until is not None and self.valid_until <= self.assessed_on:
            raise ValidationError("a competency lasts longer than a day", badge=self.badge)

    @property
    def window(self) -> DateRange:
        end = self.valid_until or date.fromordinal(
            self.assessed_on.toordinal() + REASSESSMENT_INTERVAL_DAYS
        )
        return DateRange(self.assessed_on, end)

    def current_on(self, day: date) -> bool:
        return self.window.contains(day)

    def days_left(self, day: date) -> int:
        end = self.window.end
        assert end is not None
        return end.toordinal() - day.toordinal()

    def describe(self) -> str:
        return f"{self.badge} {self.task.label} assessed {self.assessed_on} by {self.assessor}"


@dataclass(frozen=True)
class CompetencyFile:
    """Every assessment the department holds."""

    entries: tuple[Competency, ...] = ()

    @classmethod
    def of(cls, entries: Iterable[Competency]) -> CompetencyFile:
        return cls(tuple(entries))

    def with_entry(self, entry: Competency) -> CompetencyFile:
        return CompetencyFile((*self.entries, entry))

    def for_badge(self, badge: str) -> tuple[Competency, ...]:
        wanted = badge_number(badge)
        return tuple(entry for entry in self.entries if entry.badge == wanted)

    def current(self, badge: str, task: Task, day: date) -> Competency | None:
        found = [
            entry for entry in self.for_badge(badge) if entry.task is task and entry.current_on(day)
        ]
        if not found:
            return None
        return max(found, key=lambda entry: entry.assessed_on)

    def holds(self, badge: str, task: Task, day: date) -> bool:
        return self.current(badge, task, day) is not None

    def refusal(self, badge: str, task: Task, day: date) -> str | None:
        """Why this badge may not do this task today, or None."""
        if self.holds(badge, task, day):
            return None
        ever = [entry for entry in self.for_badge(badge) if entry.task is task]
        if not ever:
            return f"{badge_number(badge)} has never been assessed on {task.label}"
        latest = max(ever, key=lambda entry: entry.assessed_on)
        end = latest.window.end
        return f"{latest.badge} lapsed on {task.label} on {end}"

    def valid_assessor(self, badge: str, task: Task, day: date) -> bool:
        """An assessor has to hold the competency they are signing off."""
        return self.holds(badge, task, day)

    def due_within(self, day: date, days: int) -> tuple[Competency, ...]:
        if days < 0:
            raise ValidationError("that is not a number of days", days=days)
        found: list[Competency] = []
        seen: set[tuple[str, Task]] = set()
        for entry in sorted(self.entries, key=lambda item: item.assessed_on, reverse=True):
            key = (entry.badge, entry.task)
            if key in seen:
                continue
            seen.add(key)
            if entry.current_on(day) and entry.days_left(day) <= days:
                found.append(entry)
        return tuple(sorted(found, key=lambda item: (item.badge, item.task.value)))
