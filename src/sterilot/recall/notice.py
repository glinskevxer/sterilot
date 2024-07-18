"""Turning a recall scope into a list of things somebody has to do.

The scope says which loads are suspect. The notice says what to do about each
tray in them, and that depends entirely on where the tray is now. A tray on the
shelf gets quarantined and nobody outside the department needs to know. The
same tray already used on a patient is a conversation with infection
prevention and the surgeon, and it is the one case where the department cannot
fix its own mistake.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import asset_tag, badge_number, normalise_code
from sterilot.recall.scope import RecallScope


class Whereabouts(Enum):
    """Where a recalled tray turned out to be."""

    STORAGE = "storage"
    ISSUED = "issued"
    USED = "used"
    REPROCESSING = "reprocessing"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return self.value

    @property
    def urgency(self) -> int:
        """Lower sorts first on the notice, because it matters more."""
        return {"used": 0, "issued": 1, "storage": 2, "unknown": 3, "reprocessing": 4}[self.value]

    @property
    def action(self) -> str:
        return {
            "used": "notify infection prevention and the surgeon of record",
            "issued": "retrieve from the room before the case starts",
            "storage": "pull from the shelf and quarantine",
            "unknown": "locate the tray",
            "reprocessing": "no action, the tray is already back in the loop",
        }[self.value]

    @property
    def needs_action(self) -> bool:
        return self is not Whereabouts.REPROCESSING

    @classmethod
    def named(cls, value: str) -> Whereabouts:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such whereabouts", value=value)


@dataclass(frozen=True)
class RecallAction:
    """One tray, where it is, and what to do about it."""

    asset: str
    load: str
    where: Whereabouts
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))

    def describe(self) -> str:
        where = f"{self.where.label}"
        if self.detail:
            where = f"{where} ({self.detail})"
        return f"{self.asset} in {self.load}, {where}: {self.where.action}"

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class RecallNotice:
    """A scope, plus what has to happen to every tray in it."""

    reference: str
    raised_at: datetime
    raised_by: str
    scope: RecallScope
    actions: tuple[RecallAction, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="recall reference")
        )
        object.__setattr__(self, "raised_by", badge_number(self.raised_by))

    @property
    def patient_exposure(self) -> bool:
        """True when at least one recalled tray was already used."""
        return any(action.where is Whereabouts.USED for action in self.actions)

    def outstanding(self) -> tuple[RecallAction, ...]:
        return tuple(action for action in self.actions if action.where.needs_action)

    def by_whereabouts(self, where: Whereabouts) -> tuple[RecallAction, ...]:
        return tuple(action for action in self.actions if action.where is where)

    def render(self) -> str:
        lines = [
            f"recall {self.reference} raised {self.raised_at:%Y-%m-%d %H:%M} by {self.raised_by}",
            self.scope.summary(),
        ]
        if self.patient_exposure:
            lines.append("PATIENT EXPOSURE: at least one recalled tray was used")
        lines.extend(action.describe() for action in self.actions)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.render()


def notice_for(
    reference: str,
    scope: RecallScope,
    locations: Mapping[str, tuple[Whereabouts, str]] | Mapping[str, Whereabouts],
    raised_at: datetime,
    raised_by: str,
) -> RecallNotice:
    """Build the notice for a scope, given where each tray is now.

    A tray the location map says nothing about is not left off. It becomes an
    unknown, which is an action rather than a silence.
    """
    actions: list[RecallAction] = []
    for record in scope.loads:
        for asset in record.load.assets():
            found = locations.get(asset)
            if found is None:
                where, detail = Whereabouts.UNKNOWN, ""
            elif isinstance(found, Whereabouts):
                where, detail = found, ""
            else:
                where, detail = found
            actions.append(RecallAction(asset, record.reference, where, detail))
    actions.sort(key=lambda action: (action.where.urgency, action.asset))
    return RecallNotice(reference, raised_at, raised_by, scope, tuple(actions))
