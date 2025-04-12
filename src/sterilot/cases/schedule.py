"""The operating schedule, as the department needs to read it.

Theatre plans its day in rooms and start times. The department plans its day in
sets, and the translation between the two is the whole job: eleven cases in
four rooms is not eleven trays, it is whatever the cards add up to, arriving
before the case rather than during it.

Nothing here books a case. The schedule is somebody else's system and this is a
copy of it, which is why a double booked room is reported rather than refused.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sterilot.cases.preference_card import CardFile
from sterilot.errors import ValidationError
from sterilot.ids import case_number, normalise_code
from sterilot.interval import Window


@dataclass(frozen=True)
class ScheduledCase:
    """One case, as theatre has it."""

    case: str
    room: str
    surgeon: str
    procedure: str
    starts_at: datetime
    minutes: int
    card_reference: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "case", case_number(self.case))
        object.__setattr__(self, "room", normalise_code(self.room, field="room"))
        if self.card_reference:
            object.__setattr__(
                self, "card_reference", normalise_code(self.card_reference, field="card reference")
            )
        if not self.surgeon.strip():
            raise ValidationError("a case names a surgeon", case=self.case)
        if not self.procedure.strip():
            raise ValidationError("a case names a procedure", case=self.case)
        if self.minutes < 1:
            raise ValidationError("a case takes time", case=self.case)

    @property
    def window(self) -> Window:
        return Window.of_minutes(self.starts_at, self.minutes)

    @property
    def day(self) -> date:
        return self.starts_at.date()

    def ready_by(self, lead_minutes: int = 60) -> datetime:
        """When the department has to have the trays in the room."""
        return self.starts_at - timedelta(minutes=lead_minutes)

    def describe(self) -> str:
        return (
            f"{self.starts_at:%H:%M} {self.room} {self.surgeon} {self.procedure}"
            f" ({self.minutes} min)"
        )


@dataclass(frozen=True)
class Schedule:
    """A copy of theatre's list."""

    cases: tuple[ScheduledCase, ...] = ()

    @classmethod
    def of(cls, cases: Iterable[ScheduledCase]) -> Schedule:
        return cls(tuple(sorted(cases, key=lambda item: (item.starts_at, item.room))))

    def with_case(self, case: ScheduledCase) -> Schedule:
        return Schedule.of((*self.cases, case))

    def on_day(self, day: date) -> tuple[ScheduledCase, ...]:
        return tuple(case for case in self.cases if case.day == day)

    def in_room(self, room: str, day: date | None = None) -> tuple[ScheduledCase, ...]:
        wanted = normalise_code(room, field="room")
        found = tuple(case for case in self.cases if case.room == wanted)
        if day is None:
            return found
        return tuple(case for case in found if case.day == day)

    def rooms(self, day: date) -> tuple[str, ...]:
        return tuple(sorted({case.room for case in self.on_day(day)}))

    def overlaps(self, day: date) -> tuple[tuple[ScheduledCase, ScheduledCase], ...]:
        """Pairs of cases booked into the same room at the same time."""
        found: list[tuple[ScheduledCase, ScheduledCase]] = []
        cases = self.on_day(day)
        for index, first in enumerate(cases):
            for second in cases[index + 1 :]:
                if first.room == second.room and first.window.overlaps(second.window):
                    found.append((first, second))
        return tuple(found)

    def demand(self, cards: CardFile, day: date) -> dict[str, int]:
        """How many of each set the day's list calls for, at its busiest."""
        wanted: dict[str, int] = {}
        for case in self.on_day(day):
            if not case.card_reference:
                continue
            try:
                card = cards.for_reference(case.card_reference, day)
            except Exception:
                continue
            for code, quantity in card.wanted().items():
                wanted[code] = wanted.get(code, 0) + quantity
        return wanted

    def unattached(self, day: date) -> tuple[ScheduledCase, ...]:
        """Cases with no preference card, which the department cannot pick for."""
        return tuple(case for case in self.on_day(day) if not case.card_reference)

    def first_start(self, day: date) -> datetime | None:
        cases = self.on_day(day)
        return cases[0].starts_at if cases else None
