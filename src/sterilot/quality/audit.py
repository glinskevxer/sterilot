"""The audit trail, which has to be worth reading three years later.

Two things make an audit trail useless. Gaps, and the suspicion that somebody
edited it. The first is a discipline problem and this module cannot fix it. The
second it can: each entry carries the digest of the one before, so an entry
removed or altered in the middle shows up as a break in the chain rather than
as nothing at all.

None of this is a security control. Anyone who can rewrite the file can
recompute the chain. It is there so that an accidental loss, which is far more
common, does not pass unnoticed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sterilot.errors import ConflictError, ValidationError
from sterilot.ids import badge_number

GENESIS = "0" * 64


class Action(Enum):
    """What somebody did."""

    RECORDED = "recorded"
    AMENDED = "amended"
    RELEASED = "released"
    HELD = "held"
    REJECTED = "rejected"
    RECALLED = "recalled"
    OVERRIDDEN = "overridden"
    CLOSED = "closed"

    @property
    def label(self) -> str:
        return self.value

    @property
    def needs_reason(self) -> bool:
        """The actions somebody will be asked to justify."""
        return self in {Action.AMENDED, Action.OVERRIDDEN, Action.RECALLED}

    @classmethod
    def named(cls, value: str) -> Action:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such action", value=value)


@dataclass(frozen=True)
class AuditEvent:
    """One entry, chained to the one before it."""

    at: datetime
    by: str
    action: Action
    subject_kind: str
    subject: str
    detail: str = ""
    previous: str = GENESIS

    def __post_init__(self) -> None:
        object.__setattr__(self, "by", badge_number(self.by))
        if not self.subject_kind.strip():
            raise ValidationError("an audit entry names what kind of thing it is about")
        if not self.subject.strip():
            raise ValidationError("an audit entry names its subject")
        if self.action.needs_reason and not self.detail.strip():
            raise ValidationError("that action is recorded with a reason", action=self.action.value)

    def canonical(self) -> str:
        return "|".join(
            [
                self.at.isoformat(timespec="seconds"),
                self.by,
                self.action.value,
                self.subject_kind,
                self.subject,
                self.detail,
                self.previous,
            ]
        )

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()

    def describe(self) -> str:
        because = f", {self.detail}" if self.detail else ""
        return (
            f"{self.at:%Y-%m-%d %H:%M} {self.by} {self.action.label} "
            f"{self.subject_kind} {self.subject}{because}"
        )

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class AuditTrail:
    """An append only run of entries."""

    events: tuple[AuditEvent, ...] = ()

    @property
    def head(self) -> str:
        return self.events[-1].digest() if self.events else GENESIS

    def record(
        self,
        at: datetime,
        by: str,
        action: Action,
        subject_kind: str,
        subject: str,
        detail: str = "",
    ) -> AuditTrail:
        """Append an entry chained to the current head."""
        if self.events and at < self.events[-1].at:
            raise ConflictError("an audit entry cannot predate the one before it")
        event = AuditEvent(at, by, action, subject_kind, subject, detail, self.head)
        return AuditTrail((*self.events, event))

    def broken_at(self) -> int | None:
        """Index of the first entry whose chain does not hold, or None."""
        expected = GENESIS
        for index, event in enumerate(self.events):
            if event.previous != expected:
                return index
            expected = event.digest()
        return None

    def intact(self) -> bool:
        return self.broken_at() is None

    def for_subject(self, subject_kind: str, subject: str) -> tuple[AuditEvent, ...]:
        return tuple(
            event
            for event in self.events
            if event.subject_kind == subject_kind and event.subject == subject
        )

    def by_badge(self, badge: str) -> tuple[AuditEvent, ...]:
        wanted = badge_number(badge)
        return tuple(event for event in self.events if event.by == wanted)

    def of_action(self, action: Action) -> tuple[AuditEvent, ...]:
        return tuple(event for event in self.events if event.action is action)

    def between(self, start: datetime, end: datetime) -> tuple[AuditEvent, ...]:
        if end < start:
            raise ValidationError("that window runs backwards")
        return tuple(event for event in self.events if start <= event.at < end)

    def render(self) -> str:
        return "\n".join(event.describe() for event in self.events)


def rebuild(events: Iterable[AuditEvent]) -> AuditTrail:
    """Re-chain a run of entries read back from storage, in the order given."""
    trail = AuditTrail()
    for event in events:
        trail = trail.record(
            event.at, event.by, event.action, event.subject_kind, event.subject, event.detail
        )
    return trail
