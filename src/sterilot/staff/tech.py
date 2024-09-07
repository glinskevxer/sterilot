"""Technicians, their roles and their certifications.

Every record in this system is signed by a badge number, and a badge number is
only worth something if it belongs to somebody who was allowed to do the thing.
A trainee may assemble a tray and may not release a load. A certification that
lapsed in March does not cover a signature in April.

Roles are deliberately coarse. The department has four of them and the fine
grained question, whether this person may do this specific thing, is answered
by the competency record rather than by the job title.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import badge_number, normalise_code
from sterilot.interval import DateRange


class Role(Enum):
    """What the department has hired somebody as."""

    TRAINEE = "trainee"
    TECHNICIAN = "technician"
    LEAD = "lead"
    SUPERVISOR = "supervisor"

    @property
    def label(self) -> str:
        return self.value

    @property
    def rank(self) -> int:
        return list(Role).index(self)

    @property
    def may_release(self) -> bool:
        """A trainee never signs a release, however well they are doing."""
        return self.rank >= Role.TECHNICIAN.rank

    @property
    def may_authorise_early_release(self) -> bool:
        return self.rank >= Role.LEAD.rank

    @property
    def may_close_a_recall(self) -> bool:
        return self is Role.SUPERVISOR

    @classmethod
    def named(cls, value: str) -> Role:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such role", value=value)


@dataclass(frozen=True)
class Certification:
    """One certification, with the window it covers."""

    body: str
    number: str
    held: DateRange

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", normalise_code(self.body, field="certifying body"))
        object.__setattr__(self, "number", normalise_code(self.number, field="certificate number"))

    def current_on(self, day: date) -> bool:
        return self.held.contains(day)

    def describe(self) -> str:
        return f"{self.body} {self.number} {self.held.format()}"


@dataclass(frozen=True)
class Technician:
    """One person on the floor."""

    badge: str
    name: str
    role: Role = Role.TECHNICIAN
    employed: DateRange | None = None
    certifications: tuple[Certification, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "badge", badge_number(self.badge))
        if not self.name.strip():
            raise ValidationError("a technician has a name", badge=self.badge)

    def employed_on(self, day: date) -> bool:
        if self.employed is None:
            return True
        return self.employed.contains(day)

    def certified_on(self, day: date) -> bool:
        return any(item.current_on(day) for item in self.certifications)

    def current_certifications(self, day: date) -> tuple[Certification, ...]:
        return tuple(item for item in self.certifications if item.current_on(day))

    def refusal_to_release(self, day: date) -> str | None:
        """Why this person may not sign a release today, or None."""
        if not self.employed_on(day):
            return "the badge is not employed on that day"
        if not self.role.may_release:
            return f"a {self.role.label} does not sign a release"
        if not self.certified_on(day):
            return "the certification is not current"
        return None

    def may_release(self, day: date) -> bool:
        return self.refusal_to_release(day) is None

    def refusal_to_authorise(self, day: date) -> str | None:
        refusal = self.refusal_to_release(day)
        if refusal is not None:
            return refusal
        if not self.role.may_authorise_early_release:
            return f"a {self.role.label} does not authorise an early release"
        return None

    def with_certification(self, certification: Certification) -> Technician:
        return Technician(
            self.badge,
            self.name,
            self.role,
            self.employed,
            (*self.certifications, certification),
        )

    def label(self) -> str:
        return f"{self.badge} {self.name}"

    def __str__(self) -> str:
        return self.label()


@dataclass(frozen=True)
class Roster:
    """Everyone the department employs."""

    people: tuple[Technician, ...] = ()

    @classmethod
    def of(cls, people: Iterable[Technician]) -> Roster:
        roster = cls()
        for person in people:
            roster = roster.with_person(person)
        return roster

    def with_person(self, person: Technician) -> Roster:
        if any(item.badge == person.badge for item in self.people):
            raise ConflictError("that badge is already on the roster", badge=person.badge)
        return Roster((*self.people, person))

    def get(self, badge: str) -> Technician:
        wanted = badge_number(badge)
        for person in self.people:
            if person.badge == wanted:
                return person
        raise NotFoundError("no such badge", badge=wanted)

    def on_duty(self, day: date) -> tuple[Technician, ...]:
        return tuple(person for person in self.people if person.employed_on(day))

    def who_may_release(self, day: date) -> tuple[Technician, ...]:
        return tuple(person for person in self.on_duty(day) if person.may_release(day))

    def lapsing_within(self, day: date, days: int) -> tuple[Technician, ...]:
        """Anyone whose last current certification runs out inside ``days``."""
        if days < 0:
            raise ValidationError("that is not a number of days", days=days)
        horizon = date.fromordinal(day.toordinal() + days)
        found: list[Technician] = []
        for person in self.on_duty(day):
            current = person.current_certifications(day)
            if not current:
                continue
            ends = [item.held.end for item in current if item.held.end is not None]
            if ends and len(ends) == len(current) and min(ends) <= horizon:
                found.append(person)
        return tuple(found)
