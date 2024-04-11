"""Where a tray is in the loop, and which moves are legal.

The loop is soiled, decontamination, assembly, sterilizer, cooling, sterile
storage, issue, use, soiled again. Writing it out as a transition table rather
than a status field with an honour system is what stops a tray appearing in
sterile storage having never been through a chamber.

Quarantine and out of service are reachable from anywhere, because a recall or
a dropped tray does not wait for a convenient point in the loop. Coming back is
not free: both of them land on soiled, so the tray goes round again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sterilot.errors import ConflictError, ValidationError
from sterilot.ids import badge_number


class Stage(Enum):
    """Where a tray is right now."""

    SOILED = "soiled"
    DECONTAMINATION = "decontamination"
    CLEAN = "clean"
    ASSEMBLED = "assembled"
    STERILIZING = "sterilizing"
    COOLING = "cooling"
    STERILE = "sterile"
    ISSUED = "issued"
    IN_USE = "in_use"
    QUARANTINED = "quarantined"
    OUT_OF_SERVICE = "out_of_service"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def is_sterile(self) -> bool:
        """The stages where the contents are claimed sterile."""
        return self in {Stage.STERILE, Stage.ISSUED}

    @property
    def is_available(self) -> bool:
        """Could be picked for a case right now."""
        return self is Stage.STERILE

    @property
    def needs_reprocessing(self) -> bool:
        return self in {Stage.SOILED, Stage.IN_USE, Stage.QUARANTINED}

    @classmethod
    def named(cls, value: str) -> Stage:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such stage", value=value)


_ORDINARY: dict[Stage, frozenset[Stage]] = {
    Stage.SOILED: frozenset({Stage.DECONTAMINATION}),
    Stage.DECONTAMINATION: frozenset({Stage.CLEAN, Stage.SOILED}),
    Stage.CLEAN: frozenset({Stage.ASSEMBLED, Stage.DECONTAMINATION}),
    Stage.ASSEMBLED: frozenset({Stage.STERILIZING, Stage.CLEAN}),
    Stage.STERILIZING: frozenset({Stage.COOLING, Stage.SOILED}),
    Stage.COOLING: frozenset({Stage.STERILE, Stage.SOILED}),
    Stage.STERILE: frozenset({Stage.ISSUED, Stage.SOILED}),
    Stage.ISSUED: frozenset({Stage.IN_USE, Stage.STERILE, Stage.SOILED}),
    Stage.IN_USE: frozenset({Stage.SOILED}),
    Stage.QUARANTINED: frozenset({Stage.SOILED}),
    Stage.OUT_OF_SERVICE: frozenset({Stage.SOILED}),
}

_ALWAYS_REACHABLE = frozenset({Stage.QUARANTINED, Stage.OUT_OF_SERVICE})


def allowed_from(stage: Stage) -> frozenset[Stage]:
    """Every stage reachable from ``stage`` in one move."""
    return _ORDINARY[stage] | (_ALWAYS_REACHABLE - {stage})


def may_move(current: Stage, target: Stage) -> bool:
    return target in allowed_from(current)


def check_move(current: Stage, target: Stage) -> None:
    """Raise :class:`ConflictError` on an illegal move."""
    if current is target:
        raise ConflictError("the tray is already there", stage=current.value)
    if not may_move(current, target):
        raise ConflictError(
            "that is not a move a tray can make",
            current=current.value,
            target=target.value,
        )


@dataclass(frozen=True)
class TrayEvent:
    """One move, with who made it and why."""

    at: datetime
    stage: Stage
    by: str
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "by", badge_number(self.by))

    def describe(self) -> str:
        because = f", {self.note}" if self.note else ""
        return f"{self.at:%Y-%m-%d %H:%M} {self.stage.label} by {self.by}{because}"

    def __str__(self) -> str:
        return self.describe()


def route(start: Stage, target: Stage) -> tuple[Stage, ...]:
    """The shortest legal run of stages from ``start`` to ``target``.

    Used by the floor display to say what still has to happen before a tray is
    available, and by nothing that writes records.
    """
    if start is target:
        return (start,)
    seen = {start}
    queue: list[tuple[Stage, tuple[Stage, ...]]] = [(start, (start,))]
    while queue:
        stage, path = queue.pop(0)
        for nxt in sorted(allowed_from(stage), key=lambda item: item.value):
            if nxt in seen:
                continue
            if nxt is target:
                return (*path, nxt)
            seen.add(nxt)
            queue.append((nxt, (*path, nxt)))
    raise ConflictError("no route between those stages", start=start.value, target=target.value)
