"""Event related sterility, and the events that end it.

The department does not put a use by date on a wrapped tray, because time in a
cupboard is not what makes a package unsterile. Handling is. A pack that was
dropped is compromised on the day it was dropped whether that was yesterday or
a year ago, and a pack that has sat untouched on a closed shelf since March is
as sterile as it was in March.

Some hospitals run a date anyway, usually because their storage is not good
enough to defend the event based argument. That is a setting rather than a
belief, so both work here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber, asset_tag, badge_number
from sterilot.settings import Settings


class Packaging(Enum):
    """What the set is wrapped in, which decides how it can be spoiled."""

    SEQUENTIAL_WRAP = "sequential_wrap"
    POUCH = "pouch"
    RIGID_CONTAINER = "rigid_container"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def shows_damage(self) -> bool:
        """A tear in wrap is visible. A hairline crack in a container is not."""
        return self is not Packaging.RIGID_CONTAINER

    @classmethod
    def named(cls, value: str) -> Packaging:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such packaging", value=value)


class Event(Enum):
    """Something that happened to a package after it left the chamber."""

    DROPPED = "dropped"
    WET = "wet"
    TORN = "torn"
    SEAL_BROKEN = "seal_broken"
    COMPRESSED = "compressed"
    MOVED = "moved"
    INSPECTED = "inspected"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def compromises(self) -> bool:
        """Moving a pack and looking at it are not events that end sterility."""
        return self not in {Event.MOVED, Event.INSPECTED}

    @classmethod
    def named(cls, value: str) -> Event:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such event", value=value)


@dataclass(frozen=True)
class EventRecord:
    """One thing that happened, and who saw it."""

    event: Event
    at: datetime
    by: str
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "by", badge_number(self.by))

    def describe(self) -> str:
        because = f", {self.note}" if self.note else ""
        return f"{self.at:%Y-%m-%d %H:%M} {self.event.label} by {self.by}{because}"


@dataclass(frozen=True)
class Package:
    """One wrapped set on a shelf."""

    asset: str
    lot: LotControlNumber
    packaging: Packaging
    sterilized_at: datetime
    events: tuple[EventRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        for record in self.events:
            if record.at < self.sterilized_at:
                raise ValidationError(
                    "an event cannot predate the cycle", asset=self.asset, event=record.event.value
                )

    @classmethod
    def of(
        cls,
        asset: str,
        lot: LotControlNumber,
        packaging: Packaging,
        sterilized_at: datetime,
        events: Iterable[EventRecord] = (),
    ) -> Package:
        return cls(asset, lot, packaging, sterilized_at, tuple(events))

    def with_event(self, record: EventRecord) -> Package:
        return Package(
            self.asset, self.lot, self.packaging, self.sterilized_at, (*self.events, record)
        )

    def compromising_events(self) -> tuple[EventRecord, ...]:
        return tuple(record for record in self.events if record.event.compromises)

    def expires_on(self, settings: Settings) -> date | None:
        """The shelf life date, or None where sterility is event related."""
        if settings.shelf_life_days is None:
            return None
        return (self.sterilized_at + timedelta(days=settings.shelf_life_days)).date()

    def problems(self, settings: Settings, now: datetime) -> tuple[str, ...]:
        """Every reason this package may not go to a case."""
        if now < self.sterilized_at:
            raise ValidationError("that moment is before the package existed", asset=self.asset)
        found: list[str] = []
        for record in self.compromising_events():
            found.append(f"{record.event.label} on {record.at:%Y-%m-%d}")
        expiry = self.expires_on(settings)
        if expiry is not None and now.date() >= expiry:
            found.append(f"the shelf life ran out on {expiry.isoformat()}")
        return tuple(found)

    def sterile(self, settings: Settings, now: datetime) -> bool:
        return not self.problems(settings, now)

    def age(self, now: datetime) -> timedelta:
        return now - self.sterilized_at

    def label(self) -> str:
        return f"{self.asset} {self.lot.format()}"

    def __str__(self) -> str:
        return self.label()


def compromised(
    packages: Iterable[Package], settings: Settings, now: datetime
) -> tuple[Package, ...]:
    """Every package on the shelf that should not be there."""
    return tuple(package for package in packages if not package.sterile(settings, now))
