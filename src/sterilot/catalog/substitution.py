"""Approved substitutions.

When an item is at the repair vendor, the bench does not just put something
similar in the tray. A substitution has to be on the list, and the list is
dated, because approvals expire when the original comes back into stock.

Two rules that look pedantic and are not. Substitutions do not chain: if B may
stand in for A and C may stand in for B, that does not make C acceptable in a
tray that calls for A, because nobody has looked at whether C does the job A is
in the set to do. And a substitution is directional, so an approval to put B in
for A says nothing about putting A in for B.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sterilot.errors import ConflictError, ValidationError
from sterilot.ids import badge_number, catalog_number
from sterilot.interval import DateRange


@dataclass(frozen=True)
class Substitution:
    """One approval: ``replacement`` may stand in for ``original``."""

    original: str
    replacement: str
    approved_by: str
    effective: DateRange
    ratio: int = 1
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "original", catalog_number(self.original))
        object.__setattr__(self, "replacement", catalog_number(self.replacement))
        object.__setattr__(self, "approved_by", badge_number(self.approved_by))
        if self.original == self.replacement:
            raise ValidationError("an item cannot substitute for itself", catalog=self.original)
        if self.ratio < 1:
            raise ValidationError("a substitution ratio is at least one", ratio=self.ratio)

    def active_on(self, day: date) -> bool:
        return self.effective.contains(day)

    def quantity_for(self, wanted: int) -> int:
        """How many replacements cover ``wanted`` of the original."""
        if wanted < 0:
            raise ValidationError("cannot substitute a negative quantity", wanted=wanted)
        return wanted * self.ratio

    def describe(self) -> str:
        ratio = "" if self.ratio == 1 else f" at {self.ratio} for 1"
        because = f", {self.reason}" if self.reason else ""
        return f"{self.replacement} for {self.original}{ratio}{because}"

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class SubstitutionTable:
    """Every approval the department holds."""

    entries: tuple[Substitution, ...] = ()

    def __post_init__(self) -> None:
        seen: set[tuple[str, str, date]] = set()
        for entry in self.entries:
            key = (entry.original, entry.replacement, entry.effective.start)
            if key in seen:
                raise ConflictError(
                    "the same substitution is approved twice from the same day",
                    original=entry.original,
                    replacement=entry.replacement,
                )
            seen.add(key)

    @classmethod
    def of(cls, entries: Iterable[Substitution]) -> SubstitutionTable:
        return cls(tuple(entries))

    def with_entry(self, entry: Substitution) -> SubstitutionTable:
        return SubstitutionTable((*self.entries, entry))

    def active(self, day: date) -> tuple[Substitution, ...]:
        return tuple(entry for entry in self.entries if entry.active_on(day))

    def for_original(self, catalog: str, day: date) -> tuple[Substitution, ...]:
        wanted = catalog_number(catalog)
        return tuple(entry for entry in self.active(day) if entry.original == wanted)

    def find(self, original: str, replacement: str, day: date) -> Substitution | None:
        wanted_original = catalog_number(original)
        wanted_replacement = catalog_number(replacement)
        for entry in self.active(day):
            if entry.original == wanted_original and entry.replacement == wanted_replacement:
                return entry
        return None

    def accepts(self, original: str, replacement: str, day: date) -> bool:
        """Directional, and never transitive."""
        return self.find(original, replacement, day) is not None

    def replacements_for(self, catalog: str, day: date) -> tuple[str, ...]:
        return tuple(entry.replacement for entry in self.for_original(catalog, day))

    def retire(self, original: str, replacement: str, on: date) -> SubstitutionTable:
        """Close every open approval for that pair on ``on``."""
        wanted_original = catalog_number(original)
        wanted_replacement = catalog_number(replacement)
        changed: list[Substitution] = []
        touched = False
        for entry in self.entries:
            matches = (
                entry.original == wanted_original
                and entry.replacement == wanted_replacement
                and entry.effective.open_ended
            )
            if matches:
                touched = True
                changed.append(
                    Substitution(
                        entry.original,
                        entry.replacement,
                        entry.approved_by,
                        entry.effective.closed_at(on),
                        entry.ratio,
                        entry.reason,
                    )
                )
            else:
                changed.append(entry)
        if not touched:
            raise ValidationError(
                "no open approval for that pair",
                original=wanted_original,
                replacement=wanted_replacement,
            )
        return SubstitutionTable(tuple(changed))
