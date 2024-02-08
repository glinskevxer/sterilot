"""Time as the department keeps it.

Everything here is local wall clock time, naive, because that is what the
sterilizer printers, the washer exports and the paper logs all use, and a
record that disagrees with the paper next to it is worse than useless during an
inspection.

The one piece of real logic is the processing day. Third shift starts before
midnight and finishes after it, so a load run at half past one in the morning
belongs to the shift that started the evening before, and the daily test that
covers it is the one that ran at the start of that shift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum

from sterilot.errors import ValidationError

DAY_ROLLOVER = time(7, 0)
"""The clock time a processing day starts. Third shift ends here."""

_MOMENT_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%m/%d/%Y %H:%M",
    "%m/%d/%y %H:%M",
)
_DAY_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y")
_DURATION_DAYS = re.compile(r"^\s*(?P<value>\d+)\s*d(?:ay|ays)?\s*$", re.IGNORECASE)


class Shift(Enum):
    """The three shifts the department runs."""

    FIRST = "first"
    SECOND = "second"
    THIRD = "third"

    @property
    def label(self) -> str:
        return {"first": "days", "second": "evenings", "third": "nights"}[self.value]

    @property
    def starts_at(self) -> time:
        return {"first": time(7, 0), "second": time(15, 0), "third": time(23, 0)}[self.value]

    @classmethod
    def named(cls, value: str) -> Shift:
        wanted = value.strip().lower()
        for shift in cls:
            if wanted in {shift.value, shift.label}:
                return shift
        raise ValidationError("no such shift", value=value)


def shift_at(moment: datetime) -> Shift:
    """Which shift was on the floor at ``moment``."""
    clock = moment.time()
    if Shift.FIRST.starts_at <= clock < Shift.SECOND.starts_at:
        return Shift.FIRST
    if Shift.SECOND.starts_at <= clock < Shift.THIRD.starts_at:
        return Shift.SECOND
    return Shift.THIRD


def processing_day(moment: datetime) -> date:
    """The day a record belongs to, with third shift kept whole."""
    if moment.time() < DAY_ROLLOVER:
        return (moment - timedelta(days=1)).date()
    return moment.date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """The half open window ``[start, end)`` of a processing day."""
    start = datetime.combine(day, DAY_ROLLOVER)
    return start, start + timedelta(days=1)


def within_day(moment: datetime, day: date) -> bool:
    start, end = day_bounds(day)
    return start <= moment < end


def parse_moment(text: str) -> datetime:
    """Read a timestamp in any of the shapes our sources write."""
    stripped = text.strip()
    for shape in _MOMENT_FORMATS:
        try:
            return datetime.strptime(stripped, shape)
        except ValueError:
            continue
    raise ValidationError("cannot read that as a timestamp", text=text)


def parse_day(text: str) -> date:
    """Read a date in any of the shapes our sources write."""
    stripped = text.strip()
    for shape in _DAY_FORMATS:
        try:
            return datetime.strptime(stripped, shape).date()
        except ValueError:
            continue
    raise ValidationError("cannot read that as a date", text=text)


def parse_days(text: str) -> int:
    """Read ``30``, ``30d`` or ``30 days`` as a whole number of days."""
    stripped = text.strip()
    if stripped.isdigit():
        return int(stripped)
    match = _DURATION_DAYS.match(stripped)
    if match is None:
        raise ValidationError("cannot read that as a number of days", text=text)
    return int(match.group("value"))


def format_moment(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def format_day(day: date) -> str:
    return day.isoformat()


@dataclass(frozen=True)
class Clock:
    """A source of the current time that tests can pin."""

    fixed: datetime | None = None

    def now(self) -> datetime:
        if self.fixed is not None:
            return self.fixed
        return datetime.now().replace(microsecond=0)

    def today(self) -> date:
        return processing_day(self.now())

    def at(self, moment: datetime) -> Clock:
        return Clock(fixed=moment)
