"""A physical tray, as opposed to the count sheet it is built to.

Two trays built to ORT-MAJOR are two assets with two histories, and the whole
point of the asset tag is that they never get confused. When a recall names a
load, it names assets.

The history is kept on the tray rather than in a side table because every
question anyone asks starts from the tray: where has it been, how long has it
been sitting there, how many times has it been round this year.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum

from sterilot.assets.lifecycle import Stage, TrayEvent, check_move
from sterilot.errors import ConflictError, ValidationError
from sterilot.ids import asset_tag, badge_number, tray_code
from sterilot.units.duration import Duration


class Ownership(Enum):
    """Whose tray it is, which decides what happens at the end of the case."""

    DEPARTMENT = "department"
    CONSIGNMENT = "consignment"
    LOANER = "loaner"

    @property
    def is_ours(self) -> bool:
        return self is Ownership.DEPARTMENT

    @property
    def must_be_returned(self) -> bool:
        return self is Ownership.LOANER

    @classmethod
    def named(cls, value: str) -> Ownership:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such ownership", value=value)


@dataclass(frozen=True)
class TrayInstance:
    """One physical tray and everywhere it has been."""

    asset: str
    code: str
    ownership: Ownership = Ownership.DEPARTMENT
    owner: str = ""
    history: tuple[TrayEvent, ...] = field(default_factory=tuple)
    retired_on: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "code", tray_code(self.code))
        if not self.ownership.is_ours and not self.owner.strip():
            raise ValidationError("a tray that is not ours has to name its owner", asset=self.asset)
        if self.ownership.is_ours and self.owner.strip():
            raise ValidationError("our own trays have no outside owner", asset=self.asset)
        if not self.history:
            raise ValidationError("a tray starts with the event that put it in service")
        for earlier, later in zip(self.history, self.history[1:], strict=False):
            if later.at < earlier.at:
                raise ValidationError("tray history is out of order", asset=self.asset)

    @classmethod
    def placed_in_service(
        cls,
        asset: str,
        code: str,
        at: datetime,
        by: str,
        ownership: Ownership = Ownership.DEPARTMENT,
        owner: str = "",
    ) -> TrayInstance:
        first = TrayEvent(at, Stage.SOILED, by, note="placed in service")
        return cls(asset, code, ownership, owner, (first,))

    @property
    def stage(self) -> Stage:
        return self.history[-1].stage

    @property
    def since(self) -> datetime:
        return self.history[-1].at

    @property
    def retired(self) -> bool:
        return self.retired_on is not None

    def moved_to(self, stage: Stage, at: datetime, by: str, note: str = "") -> TrayInstance:
        """Record a move, refusing anything the transition table does not allow."""
        if self.retired:
            raise ConflictError("that tray is retired", asset=self.asset)
        if at < self.since:
            raise ValidationError(
                "a move cannot predate the last one", asset=self.asset, at=at.isoformat()
            )
        check_move(self.stage, stage)
        event = TrayEvent(at, stage, by, note)
        return replace(self, history=(*self.history, event))

    def retired_on_day(self, day: date, by: str) -> TrayInstance:
        if self.retired:
            raise ConflictError("that tray is already retired", asset=self.asset)
        badge_number(by)
        return replace(self, retired_on=day)

    def stage_at(self, moment: datetime) -> Stage | None:
        """Where the tray was at ``moment``, or None before it existed."""
        found: Stage | None = None
        for event in self.history:
            if event.at <= moment:
                found = event.stage
            else:
                break
        return found

    def time_in_stage(self, now: datetime) -> Duration:
        if now < self.since:
            raise ValidationError("that moment is before the tray got here", asset=self.asset)
        return Duration((now - self.since).total_seconds())

    def turns_completed(self) -> int:
        """How many times the tray has reached sterile storage."""
        return sum(1 for event in self.history if event.stage is Stage.STERILE)

    def events_in(self, stage: Stage) -> tuple[TrayEvent, ...]:
        return tuple(event for event in self.history if event.stage is stage)

    def label(self) -> str:
        return f"{self.asset} ({self.code})"

    def __str__(self) -> str:
        return self.label()


def by_stage(trays: Iterable[TrayInstance]) -> dict[Stage, tuple[TrayInstance, ...]]:
    """Group trays by where they are, for the floor board."""
    grouped: dict[Stage, list[TrayInstance]] = {}
    for tray in trays:
        grouped.setdefault(tray.stage, []).append(tray)
    return {
        stage: tuple(sorted(found, key=lambda tray: tray.asset)) for stage, found in grouped.items()
    }
