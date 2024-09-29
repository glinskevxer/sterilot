"""The daily test log, which is the first thing an inspector asks to see.

Every machine owes a set of tests each day it runs, and the log's job is not
to hold the results, which live with the tests themselves. Its job is to answer
whether anything is missing. A day with no entry at all is worse than a day
with a failure, because a failure was noticed.

What a machine owes is derived rather than typed in. A prevacuum sterilizer
owes an air removal test and a biological. A gravity chamber owes the
biological only. A washer owes a cleaning verification.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from sterilot.decon.washer import Washer
from sterilot.errors import ConflictError, ValidationError
from sterilot.ids import badge_number, equipment_id
from sterilot.interval import DateRange
from sterilot.sterilizer.equipment import Sterilizer


class Duty(Enum):
    """A test a machine owes on a day it runs."""

    AIR_REMOVAL = "air_removal"
    BIOLOGICAL = "biological"
    CLEANING = "cleaning"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def named(cls, value: str) -> Duty:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such duty", value=value)


def duties_for_sterilizer(sterilizer: Sterilizer) -> frozenset[Duty]:
    duties = {Duty.BIOLOGICAL}
    if sterilizer.daily_air_removal_test:
        duties.add(Duty.AIR_REMOVAL)
    return frozenset(duties)


def duties_for_washer(washer: Washer) -> frozenset[Duty]:
    if not washer.disinfects:
        return frozenset()
    return frozenset({Duty.CLEANING})


@dataclass(frozen=True)
class LogEntry:
    """One machine, one day, one duty, one outcome."""

    day: date
    equipment: str
    duty: Duty
    passed: bool
    by: str
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        object.__setattr__(self, "by", badge_number(self.by))
        if not self.passed and not self.note.strip():
            raise ValidationError("a failure is written up", equipment=self.equipment)

    def describe(self) -> str:
        verdict = "pass" if self.passed else f"FAIL, {self.note}"
        return f"{self.day.isoformat()} {self.equipment} {self.duty.label} {verdict}"


@dataclass(frozen=True)
class DutyLog:
    """Every daily test entry."""

    entries: tuple[LogEntry, ...] = ()

    @classmethod
    def of(cls, entries: Iterable[LogEntry]) -> DutyLog:
        log = cls()
        for entry in entries:
            log = log.with_entry(entry)
        return log

    def with_entry(self, entry: LogEntry) -> DutyLog:
        clash = any(
            item.day == entry.day and item.equipment == entry.equipment and item.duty is entry.duty
            for item in self.entries
        )
        if clash:
            raise ConflictError(
                "that duty is already logged for the day",
                equipment=entry.equipment,
                day=entry.day.isoformat(),
            )
        return DutyLog((*self.entries, entry))

    def for_equipment(self, equipment: str) -> tuple[LogEntry, ...]:
        wanted = equipment_id(equipment)
        return tuple(item for item in self.entries if item.equipment == wanted)

    def on_day(self, equipment: str, day: date) -> tuple[LogEntry, ...]:
        return tuple(item for item in self.for_equipment(equipment) if item.day == day)

    def covered(self, equipment: str, day: date, duties: frozenset[Duty]) -> bool:
        """True when every duty owed that day is logged and passed."""
        done = {item.duty for item in self.on_day(equipment, day) if item.passed}
        return duties <= done

    def gaps(
        self, equipment: str, duties: frozenset[Duty], window: DateRange, ran_on: Iterable[date]
    ) -> tuple[tuple[date, Duty], ...]:
        """Duties missing on days the machine actually ran."""
        days = {day for day in ran_on if window.contains(day)}
        found: list[tuple[date, Duty]] = []
        for day in sorted(days):
            logged = {item.duty for item in self.on_day(equipment, day) if item.passed}
            for duty in sorted(duties - logged, key=lambda item: item.value):
                found.append((day, duty))
        return tuple(found)

    def failures(self, equipment: str | None = None) -> tuple[LogEntry, ...]:
        found = self.entries if equipment is None else self.for_equipment(equipment)
        return tuple(item for item in found if not item.passed)

    def last_failure(self, equipment: str, duty: Duty) -> LogEntry | None:
        found = [
            item for item in self.for_equipment(equipment) if item.duty is duty and not item.passed
        ]
        return max(found, key=lambda item: item.day) if found else None

    def clean_run(self, equipment: str, duty: Duty, until: date) -> int:
        """Consecutive days ending at ``until`` with a passing entry."""
        day = until
        run = 0
        while True:
            logged = [item for item in self.on_day(equipment, day) if item.duty is duty]
            if not logged or not all(item.passed for item in logged):
                return run
            run += 1
            day = day - timedelta(days=1)
