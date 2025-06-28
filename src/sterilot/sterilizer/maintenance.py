"""Planned maintenance, which is the work that stops the unplanned kind.

A door gasket is replaced on a schedule because replacing it after it fails
means a chamber down for two days and a morning of cancelled cases. So each
task carries its own interval, and an interval is either a number of days or a
number of cycles, because a chamber that ran forty loads last week is not in
the same state as one that ran four.

Both are allowed on one task, and the earlier of the two wins. That is the
whole point: whichever comes first.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sterilot.errors import ValidationError
from sterilot.ids import equipment_id, normalise_code


@dataclass(frozen=True)
class Task:
    """One planned job on one machine."""

    code: str
    equipment: str
    description: str
    every_days: int | None = None
    every_cycles: int | None = None
    last_done: date | None = None
    cycles_since: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="task code"))
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        if not self.description.strip():
            raise ValidationError("a task says what it is", code=self.code)
        if self.every_days is None and self.every_cycles is None:
            raise ValidationError("a task needs an interval", code=self.code)
        for value, name in ((self.every_days, "days"), (self.every_cycles, "cycles")):
            if value is not None and value < 1:
                raise ValidationError(f"an interval in {name} is at least one", code=self.code)
        if self.cycles_since < 0:
            raise ValidationError("a cycle count cannot be negative", code=self.code)

    @property
    def never_done(self) -> bool:
        return self.last_done is None

    def due_on(self) -> date | None:
        """The calendar date this falls due, or None when it is cycle driven."""
        if self.every_days is None or self.last_done is None:
            return None
        return self.last_done + timedelta(days=self.every_days)

    def cycles_left(self) -> int | None:
        if self.every_cycles is None:
            return None
        return self.every_cycles - self.cycles_since

    def due(self, day: date) -> bool:
        if self.never_done:
            return True
        calendar = self.due_on()
        if calendar is not None and day >= calendar:
            return True
        left = self.cycles_left()
        return left is not None and left <= 0

    def reason(self, day: date) -> str | None:
        """Why it is due, or None."""
        if self.never_done:
            return "never done"
        calendar = self.due_on()
        if calendar is not None and day >= calendar:
            over = (day - calendar).days
            return f"due {calendar.isoformat()}" if over == 0 else f"{over} days overdue"
        left = self.cycles_left()
        if left is not None and left <= 0:
            return f"{-left} cycles past the interval" if left < 0 else "cycle interval reached"
        return None

    def after_cycle(self) -> Task:
        from dataclasses import replace

        return replace(self, cycles_since=self.cycles_since + 1)

    def done(self, day: date) -> Task:
        from dataclasses import replace

        return replace(self, last_done=day, cycles_since=0)

    def describe(self) -> str:
        interval = []
        if self.every_days is not None:
            interval.append(f"{self.every_days} days")
        if self.every_cycles is not None:
            interval.append(f"{self.every_cycles} cycles")
        return f"{self.code} {self.description} every {' or '.join(interval)}"


@dataclass(frozen=True)
class Plan:
    """Every planned task the department holds."""

    tasks: tuple[Task, ...] = ()

    @classmethod
    def of(cls, tasks: Iterable[Task]) -> Plan:
        return cls(tuple(sorted(tasks, key=lambda item: (item.equipment, item.code))))

    def for_equipment(self, equipment: str) -> tuple[Task, ...]:
        wanted = equipment_id(equipment)
        return tuple(task for task in self.tasks if task.equipment == wanted)

    def due(self, day: date) -> tuple[Task, ...]:
        return tuple(task for task in self.tasks if task.due(day))

    def coming(self, day: date, within_days: int) -> tuple[Task, ...]:
        """Tasks not due yet that will be inside the window."""
        if within_days < 0:
            raise ValidationError("that is not a number of days", days=within_days)
        horizon = day + timedelta(days=within_days)
        found: list[Task] = []
        for task in self.tasks:
            if task.due(day):
                continue
            calendar = task.due_on()
            if calendar is not None and calendar <= horizon:
                found.append(task)
        return tuple(found)
