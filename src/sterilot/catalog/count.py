"""Counting a tray against its sheet.

This is the assembly bench in one function. A technician lays the tray out,
counts what is there, and the answer is not a number but a list of differences
that somebody has to do something about.

The substitution table changes what the count means, which is why it is an
argument and not a lookup buried inside. An approved replacement sitting in the
tray covers the shortage it was approved for and nothing else, and the same
item with no approval that day is a foreign instrument.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from sterilot.catalog.substitution import SubstitutionTable
from sterilot.catalog.tray import CountSheet
from sterilot.errors import ValidationError
from sterilot.ids import catalog_number

SHORT = "short"
EXTRA = "extra"
FOREIGN = "foreign"


@dataclass(frozen=True)
class Discrepancy:
    """One difference between the tray and the sheet."""

    catalog: str
    kind: str
    expected: int
    found: int

    @property
    def blocking(self) -> bool:
        """A short required item stops the tray. The rest are paperwork."""
        return self.kind == SHORT

    def describe(self) -> str:
        if self.kind == SHORT:
            return f"{self.catalog} short {self.expected - self.found} of {self.expected}"
        if self.kind == EXTRA:
            return f"{self.catalog} has {self.found - self.expected} more than the sheet"
        return f"{self.catalog} is not on this sheet, {self.found} found"


@dataclass(frozen=True)
class SubstitutionUsed:
    """A replacement that covered a shortage, recorded for the tray label."""

    original: str
    replacement: str
    covered: int
    consumed: int

    def describe(self) -> str:
        return f"{self.consumed} x {self.replacement} covering {self.covered} x {self.original}"


@dataclass(frozen=True)
class CountResult:
    """What the bench found."""

    code: str
    discrepancies: tuple[Discrepancy, ...]
    substitutions: tuple[SubstitutionUsed, ...]

    @property
    def complete(self) -> bool:
        """Nothing required is missing. Extras and foreigns do not stop a tray."""
        return not any(item.blocking for item in self.discrepancies)

    @property
    def exact(self) -> bool:
        return not self.discrepancies

    def shortages(self) -> tuple[Discrepancy, ...]:
        return tuple(item for item in self.discrepancies if item.kind == SHORT)

    def foreigns(self) -> tuple[Discrepancy, ...]:
        return tuple(item for item in self.discrepancies if item.kind == FOREIGN)

    def summary(self) -> str:
        if self.exact:
            return f"{self.code} counts complete"
        parts = [item.describe() for item in self.discrepancies]
        return f"{self.code}: " + "; ".join(parts)


def _normalise(counted: Mapping[str, int] | Iterable[tuple[str, int]]) -> dict[str, int]:
    pairs = counted.items() if isinstance(counted, Mapping) else counted
    tally: dict[str, int] = {}
    for catalog, quantity in pairs:
        if quantity < 0:
            raise ValidationError("a count cannot be negative", catalog=catalog, quantity=quantity)
        key = catalog_number(catalog)
        tally[key] = tally.get(key, 0) + quantity
    return tally


def count_tray(
    sheet: CountSheet,
    counted: Mapping[str, int] | Iterable[tuple[str, int]],
    substitutions: SubstitutionTable | None = None,
    day: date | None = None,
) -> CountResult:
    """Reconcile a physical count against ``sheet``."""
    table = substitutions or SubstitutionTable()
    when = day or date.today()
    remaining = _normalise(counted)
    deficits: dict[str, int] = {}
    expected: dict[str, int] = {}

    for line in sheet.lines:
        expected[line.catalog] = line.quantity
        found = remaining.get(line.catalog, 0)
        used = min(found, line.quantity)
        if used:
            remaining[line.catalog] = found - used
        short = line.quantity - used
        if short and line.required:
            deficits[line.catalog] = short

    used_substitutions: list[SubstitutionUsed] = []
    for catalog in list(deficits):
        for approval in table.for_original(catalog, when):
            outstanding = deficits[catalog]
            if outstanding == 0:
                break
            available = remaining.get(approval.replacement, 0)
            if available < approval.ratio:
                continue
            covered = min(outstanding, available // approval.ratio)
            consumed = approval.quantity_for(covered)
            remaining[approval.replacement] = available - consumed
            deficits[catalog] = outstanding - covered
            used_substitutions.append(
                SubstitutionUsed(catalog, approval.replacement, covered, consumed)
            )
        if deficits[catalog] == 0:
            del deficits[catalog]

    discrepancies: list[Discrepancy] = []
    for catalog in sorted(deficits):
        wanted = expected[catalog]
        discrepancies.append(Discrepancy(catalog, SHORT, wanted, wanted - deficits[catalog]))
    for catalog in sorted(remaining):
        left = remaining[catalog]
        if left <= 0:
            continue
        if catalog in expected:
            discrepancies.append(
                Discrepancy(catalog, EXTRA, expected[catalog], expected[catalog] + left)
            )
        else:
            discrepancies.append(Discrepancy(catalog, FOREIGN, 0, left))

    return CountResult(sheet.code, tuple(discrepancies), tuple(used_substitutions))
