"""Issuing trays to cases, and what came back.

This is the module a recall actually runs on. Everything else can say a tray
was sterile; only this can say where it went and whether anybody opened it.

The distinction that matters is between issued and used. A tray that went to a
room and came back with the wrapper intact is still sterile and goes back on
the shelf. A tray that was opened is soiled whether or not an instrument was
picked up, and a tray that was used on a patient is the case a recall cannot
undo.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import asset_tag, badge_number, case_number
from sterilot.recall.notice import Whereabouts


class Disposition(Enum):
    """What happened to a tray after it was issued."""

    OPEN = "open"
    UNOPENED = "unopened"
    OPENED = "opened"
    USED = "used"

    @property
    def label(self) -> str:
        return self.value

    @property
    def closed(self) -> bool:
        return self is not Disposition.OPEN

    @property
    def whereabouts(self) -> Whereabouts:
        return {
            "open": Whereabouts.ISSUED,
            "unopened": Whereabouts.STORAGE,
            "opened": Whereabouts.REPROCESSING,
            "used": Whereabouts.USED,
        }[self.value]

    @classmethod
    def named(cls, value: str) -> Disposition:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such disposition", value=value)


@dataclass(frozen=True)
class Issue:
    """One tray sent to one case."""

    asset: str
    case: str
    issued_at: datetime
    issued_by: str
    returned_at: datetime | None = None
    disposition: Disposition = Disposition.OPEN

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "case", case_number(self.case))
        object.__setattr__(self, "issued_by", badge_number(self.issued_by))
        if self.returned_at is not None and self.returned_at < self.issued_at:
            raise ValidationError("a tray cannot come back before it went out", asset=self.asset)
        if self.disposition.closed and self.returned_at is None:
            raise ValidationError("a closed issue records when it came back", asset=self.asset)
        if not self.disposition.closed and self.returned_at is not None:
            raise ValidationError("a returned tray needs a disposition", asset=self.asset)

    @property
    def open(self) -> bool:
        return not self.disposition.closed

    @property
    def whereabouts(self) -> Whereabouts:
        return self.disposition.whereabouts

    def returned(self, at: datetime, disposition: Disposition) -> Issue:
        if self.disposition.closed:
            raise ConflictError("that tray already came back", asset=self.asset)
        if not disposition.closed:
            raise ValidationError("a return needs a real disposition", asset=self.asset)
        return replace(self, returned_at=at, disposition=disposition)

    def describe(self) -> str:
        if self.open:
            return f"{self.asset} out to {self.case} since {self.issued_at:%Y-%m-%d %H:%M}"
        return f"{self.asset} back from {self.case} {self.disposition.label}"

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class IssueLog:
    """Every issue, which is the department's answer to where a tray is."""

    entries: tuple[Issue, ...] = ()

    @classmethod
    def of(cls, entries: Iterable[Issue]) -> IssueLog:
        return cls(tuple(sorted(entries, key=lambda item: item.issued_at)))

    def with_entry(self, entry: Issue) -> IssueLog:
        if any(item.asset == entry.asset and item.open for item in self.entries):
            raise ConflictError("that tray is already out", asset=entry.asset)
        return IssueLog.of((*self.entries, entry))

    def replacing(self, entry: Issue) -> IssueLog:
        found = False
        changed: list[Issue] = []
        for item in self.entries:
            if item.asset == entry.asset and item.issued_at == entry.issued_at:
                changed.append(entry)
                found = True
            else:
                changed.append(item)
        if not found:
            raise NotFoundError("no issue of that tray at that time", asset=entry.asset)
        return IssueLog.of(changed)

    def for_asset(self, asset: str) -> tuple[Issue, ...]:
        wanted = asset_tag(asset)
        return tuple(item for item in self.entries if item.asset == wanted)

    def for_case(self, case: str) -> tuple[Issue, ...]:
        wanted = case_number(case)
        return tuple(item for item in self.entries if item.case == wanted)

    def open_issues(self) -> tuple[Issue, ...]:
        return tuple(item for item in self.entries if item.open)

    def latest_for(self, asset: str) -> Issue | None:
        found = self.for_asset(asset)
        return found[-1] if found else None

    def whereabouts(self, asset: str) -> tuple[Whereabouts, str]:
        """Where a tray is now, in the shape the recall notice wants."""
        latest = self.latest_for(asset)
        if latest is None:
            return Whereabouts.UNKNOWN, ""
        return latest.whereabouts, latest.case

    def locations(self, assets: Iterable[str]) -> dict[str, tuple[Whereabouts, str]]:
        return {asset_tag(asset): self.whereabouts(asset) for asset in assets}

    def used_in_case(self, case: str) -> tuple[str, ...]:
        return tuple(
            item.asset for item in self.for_case(case) if item.disposition is Disposition.USED
        )
