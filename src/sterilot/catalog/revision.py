"""Count sheet revisions, and what changed between two of them.

Sets change. A surgeon asks for two more Kochers, an instrument is discontinued
and the replacement has a different catalog number, a whole level comes out
because nobody has used it since 2019. None of that is allowed to quietly
rewrite history, because a discrepancy raised against a tray assembled in March
has to be judged against the sheet that was current in March.

So a sheet is never edited. A new revision is added with an effective date and
the previous one is closed the day before.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sterilot.catalog.tray import CountSheet
from sterilot.errors import NotFoundError, ValidationError
from sterilot.ids import tray_code
from sterilot.interval import DateRange


@dataclass(frozen=True)
class Revision:
    """One version of a count sheet, with the days it was in force."""

    number: int
    sheet: CountSheet
    effective: DateRange
    note: str = ""

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValidationError("revisions are numbered from one", number=self.number)

    @property
    def code(self) -> str:
        return self.sheet.code

    @property
    def current(self) -> bool:
        return self.effective.open_ended

    def covers(self, day: date) -> bool:
        return self.effective.contains(day)

    def label(self) -> str:
        return f"{self.code} rev {self.number}"

    def __str__(self) -> str:
        return self.label()


@dataclass(frozen=True)
class LineChange:
    """One difference between two revisions of the same sheet."""

    catalog: str
    kind: str
    before: int | None
    after: int | None

    def describe(self) -> str:
        if self.kind == "added":
            return f"{self.catalog} added, {self.after}"
        if self.kind == "removed":
            return f"{self.catalog} removed, was {self.before}"
        return f"{self.catalog} changed from {self.before} to {self.after}"


@dataclass(frozen=True)
class RevisionHistory:
    """Every revision of one sheet, oldest first."""

    code: str
    revisions: tuple[Revision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", tray_code(self.code))
        if not self.revisions:
            raise ValidationError("a history needs a first revision", code=self.code)
        numbers = [revision.number for revision in self.revisions]
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            raise ValidationError("revisions are out of order", code=self.code, numbers=numbers)
        for revision in self.revisions:
            if revision.code != self.code:
                raise ValidationError(
                    "a revision belongs to a different sheet",
                    code=self.code,
                    other=revision.code,
                )
        open_ended = [revision for revision in self.revisions if revision.current]
        if len(open_ended) != 1 or not self.revisions[-1].current:
            raise ValidationError("exactly the last revision stays open", code=self.code)

    @classmethod
    def started(cls, sheet: CountSheet, effective_from: date, note: str = "") -> RevisionHistory:
        return cls(sheet.code, (Revision(1, sheet, DateRange.starting(effective_from), note),))

    @property
    def current(self) -> Revision:
        return self.revisions[-1]

    def at(self, day: date) -> Revision:
        """The revision in force on ``day``."""
        for revision in self.revisions:
            if revision.covers(day):
                return revision
        raise NotFoundError("no revision was in force then", code=self.code, day=day.isoformat())

    def numbered(self, number: int) -> Revision:
        for revision in self.revisions:
            if revision.number == number:
                return revision
        raise NotFoundError("no such revision", code=self.code, number=number)

    def revised(self, sheet: CountSheet, effective_from: date, note: str = "") -> RevisionHistory:
        """Close the current revision and open a new one on ``effective_from``."""
        if sheet.code != self.code:
            raise ValidationError("that sheet is for a different set", code=self.code)
        current = self.current
        if effective_from <= current.effective.start:
            raise ValidationError(
                "a revision cannot start before the one it replaces",
                code=self.code,
                effective_from=effective_from.isoformat(),
            )
        closed = Revision(
            current.number,
            current.sheet,
            current.effective.closed_at(effective_from),
            current.note,
        )
        fresh = Revision(current.number + 1, sheet, DateRange.starting(effective_from), note)
        return RevisionHistory(self.code, (*self.revisions[:-1], closed, fresh))

    def changes(self, earlier: int, later: int) -> tuple[LineChange, ...]:
        """What moved between two revisions, by catalog number."""
        before = {line.catalog: line.quantity for line in self.numbered(earlier).sheet.lines}
        after = {line.catalog: line.quantity for line in self.numbered(later).sheet.lines}
        changes: list[LineChange] = []
        for catalog in sorted(set(before) | set(after)):
            was = before.get(catalog)
            now = after.get(catalog)
            if was == now:
                continue
            if was is None:
                changes.append(LineChange(catalog, "added", None, now))
            elif now is None:
                changes.append(LineChange(catalog, "removed", was, None))
            else:
                changes.append(LineChange(catalog, "changed", was, now))
        return tuple(changes)


def history_for(histories: Iterable[RevisionHistory], code: str) -> RevisionHistory:
    wanted = tray_code(code)
    for history in histories:
        if history.code == wanted:
            return history
    raise NotFoundError("no count sheet with that code", code=wanted)
