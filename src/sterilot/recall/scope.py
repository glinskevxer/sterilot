"""Recall scope: how far back a failed test reaches.

The rule is not complicated and it is easy to get wrong under pressure. A
failed biological or a failed air removal test says the chamber was not working
at the moment of the test. It does not say when it stopped working, so
everything back to the last time the chamber was known good is suspect.

The last time it was known good is the previous passing test of the same kind
on the same chamber. Not a passing test on the chamber next to it, and not a
passing test of a different kind, because a Bowie Dick and a biological are not
evidence of the same thing.

With no previous passing test the window opens at the earliest load the
register holds for that chamber, because that is as far back as the evidence
goes and pretending otherwise would understate the recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import equipment_id
from sterilot.interval import Window
from sterilot.load.record import LoadRecord, LoadRegister


class Trigger(Enum):
    """Which kind of failure opened the recall."""

    BIOLOGICAL = "biological"
    AIR_REMOVAL = "air_removal"
    CLEANING = "cleaning"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def named(cls, value: str) -> Trigger:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {"bi": cls.BIOLOGICAL, "bowie_dick": cls.AIR_REMOVAL, "bd": cls.AIR_REMOVAL}
        for member in cls:
            if wanted == member.value:
                return member
        if wanted in aliases:
            return aliases[wanted]
        raise ValidationError("no such test kind", value=value)


@dataclass(frozen=True)
class QualificationEvent:
    """One test on one chamber, passed or failed."""

    equipment: str
    kind: Trigger
    at: datetime
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))


def last_pass_before(
    events: tuple[QualificationEvent, ...],
    equipment: str,
    kind: Trigger,
    moment: datetime,
) -> QualificationEvent | None:
    """The most recent passing test of the same kind on the same chamber."""
    wanted = equipment_id(equipment)
    found: QualificationEvent | None = None
    for event in sorted(events, key=lambda item: item.at):
        if event.equipment != wanted or event.kind is not kind:
            continue
        if event.at < moment and event.passed:
            found = event
    return found


@dataclass(frozen=True)
class RecallScope:
    """Everything one failed test calls into question."""

    equipment: str
    kind: Trigger
    window: Window
    loads: tuple[LoadRecord, ...]
    anchored: bool

    @property
    def load_count(self) -> int:
        return len(self.loads)

    def assets(self) -> tuple[str, ...]:
        found: list[str] = []
        for record in self.loads:
            for asset in record.load.assets():
                if asset not in found:
                    found.append(asset)
        return tuple(found)

    def released_loads(self) -> tuple[LoadRecord, ...]:
        return tuple(record for record in self.loads if record.released)

    def summary(self) -> str:
        anchor = "back to the last passing test" if self.anchored else "back to the first record"
        loads = _plural(self.load_count, "load")
        trays = _plural(len(self.assets()), "tray")
        return f"{self.equipment}: {self.kind.label} failure, {loads} {anchor}, {trays}"

    def __str__(self) -> str:
        return self.summary()


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def scope_for(
    register: LoadRegister,
    events: tuple[QualificationEvent, ...],
    failure: QualificationEvent,
) -> RecallScope:
    """Work out the recall a failed test opens."""
    if failure.passed:
        raise ValidationError("that test did not fail", equipment=failure.equipment)
    previous = last_pass_before(events, failure.equipment, failure.kind, failure.at)
    candidates = register.on_equipment(failure.equipment)
    if previous is not None:
        start = previous.at
        anchored = True
    elif candidates:
        start = min(record.cycle.started_at for record in candidates)
        anchored = False
    else:
        start = failure.at
        anchored = False
    window = Window(start, failure.at)
    caught = tuple(
        record
        for record in candidates
        if window.contains(record.cycle.started_at) or record.cycle.started_at == failure.at
    )
    return RecallScope(failure.equipment, failure.kind, window, caught, anchored)
