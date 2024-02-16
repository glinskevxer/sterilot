"""Half open windows, in dates and in moments.

Effective dates turn up everywhere: a count sheet revision, a technician's
competency, a vendor agreement, a shelf life. All of them are "from this day,
until this day, or still current". Getting the boundary wrong by one day is the
kind of error that only shows up in an audit, so the boundary lives in one
place with tests on it.

Both types are half open. The start is inside the window and the end is not.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sterilot.errors import ValidationError


@dataclass(frozen=True)
class DateRange:
    """``[start, end)`` in whole days. An absent end means still current."""

    start: date
    end: date | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end <= self.start:
            raise ValidationError(
                "a date range must end after it starts", start=self.start, end=self.end
            )

    @classmethod
    def starting(cls, start: date) -> DateRange:
        return cls(start, None)

    @classmethod
    def of_days(cls, start: date, days: int) -> DateRange:
        if days < 1:
            raise ValidationError("a date range covers at least one day", days=days)
        return cls(start, start + timedelta(days=days))

    @property
    def open_ended(self) -> bool:
        return self.end is None

    @property
    def last_day(self) -> date | None:
        """The final day inside the window, or None when it is open."""
        if self.end is None:
            return None
        return self.end - timedelta(days=1)

    def days(self) -> int | None:
        if self.end is None:
            return None
        return (self.end - self.start).days

    def contains(self, day: date) -> bool:
        if day < self.start:
            return False
        return self.end is None or day < self.end

    def overlaps(self, other: DateRange) -> bool:
        later_start = max(self.start, other.start)
        ends = [end for end in (self.end, other.end) if end is not None]
        if not ends:
            return True
        return later_start < min(ends)

    def intersection(self, other: DateRange) -> DateRange | None:
        if not self.overlaps(other):
            return None
        start = max(self.start, other.start)
        ends = [end for end in (self.end, other.end) if end is not None]
        return DateRange(start, min(ends) if ends else None)

    def closed_at(self, end: date) -> DateRange:
        """The same range with a hard end, which is how a revision retires."""
        return DateRange(self.start, end)

    def iter_days(self) -> Iterator[date]:
        if self.end is None:
            raise ValidationError("cannot walk an open ended range")
        day = self.start
        while day < self.end:
            yield day
            day += timedelta(days=1)

    def format(self) -> str:
        if self.end is None:
            return f"{self.start.isoformat()} onward"
        return f"{self.start.isoformat()} to {self.last_day}"

    def __str__(self) -> str:
        return self.format()


@dataclass(frozen=True)
class Window:
    """``[start, end)`` in moments, used for cycles and incubations."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValidationError(
                "a window cannot end before it starts", start=self.start, end=self.end
            )

    @classmethod
    def of_minutes(cls, start: datetime, minutes: float) -> Window:
        if minutes < 0:
            raise ValidationError("a window cannot run backwards", minutes=minutes)
        return cls(start, start + timedelta(minutes=minutes))

    @classmethod
    def of_hours(cls, start: datetime, hours: float) -> Window:
        return cls.of_minutes(start, hours * 60.0)

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def minutes(self) -> float:
        return self.seconds / 60.0

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def overlaps(self, other: Window) -> bool:
        return max(self.start, other.start) < min(self.end, other.end)

    def extended_by(self, minutes: float) -> Window:
        return Window(self.start, self.end + timedelta(minutes=minutes))

    def format(self) -> str:
        return f"{self.start:%Y-%m-%d %H:%M} to {self.end:%Y-%m-%d %H:%M}"

    def __str__(self) -> str:
        return self.format()


def covering(ranges: Iterable[DateRange]) -> DateRange:
    """The smallest range containing every range given."""
    items = list(ranges)
    if not items:
        raise ValidationError("nothing to cover")
    start = min(item.start for item in items)
    if any(item.end is None for item in items):
        return DateRange(start, None)
    ends = [item.end for item in items if item.end is not None]
    return DateRange(start, max(ends))
