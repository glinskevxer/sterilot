"""Picking from the shelf, oldest first.

Stock rotation is not tidiness. A package that has been on the shelf longest
has had the most chances to be knocked, leaned on or rained on by a leaking
pipe, so it is the one that should be used next while it is still good. Picking
whatever is at the front of the shelf leaves the back row ageing quietly until
somebody finds it has been there since the previous financial year.

A pick that comes up short says so rather than handing over what it found. The
room needs to know it is getting three of four.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sterilot.errors import ValidationError
from sterilot.ids import normalise_code, tray_code
from sterilot.settings import Settings
from sterilot.storage.event import Package


@dataclass(frozen=True)
class ShelfItem:
    """One package, and where it is sitting."""

    package: Package
    code: str
    location: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", tray_code(self.code))
        object.__setattr__(self, "location", normalise_code(self.location, field="location code"))

    @property
    def asset(self) -> str:
        return self.package.asset


@dataclass(frozen=True)
class Skipped:
    """A package that was passed over, and why."""

    asset: str
    reason: str

    def describe(self) -> str:
        return f"{self.asset}: {self.reason}"


@dataclass(frozen=True)
class PickResult:
    """What came off the shelf."""

    code: str
    wanted: int
    picked: tuple[ShelfItem, ...]
    skipped: tuple[Skipped, ...]

    @property
    def short(self) -> int:
        return self.wanted - len(self.picked)

    @property
    def complete(self) -> bool:
        return self.short == 0

    def assets(self) -> tuple[str, ...]:
        return tuple(item.asset for item in self.picked)

    def summary(self) -> str:
        if self.complete:
            return f"{self.code}: picked {len(self.picked)} of {self.wanted}"
        return f"{self.code}: picked {len(self.picked)} of {self.wanted}, {self.short} short"

    def __str__(self) -> str:
        return self.summary()


def pick(
    shelf: Iterable[ShelfItem],
    code: str,
    quantity: int,
    now: datetime,
    settings: Settings | None = None,
) -> PickResult:
    """Take ``quantity`` of ``code`` off the shelf, oldest usable first."""
    if quantity < 1:
        raise ValidationError("a pick asks for at least one", code=code, quantity=quantity)
    rules = settings or Settings()
    wanted_code = tray_code(code)
    candidates = [item for item in shelf if item.code == wanted_code]
    candidates.sort(key=lambda item: (item.package.sterilized_at, item.asset))

    picked: list[ShelfItem] = []
    skipped: list[Skipped] = []
    for item in candidates:
        if len(picked) == quantity:
            break
        problems = item.package.problems(rules, now)
        if problems:
            skipped.append(Skipped(item.asset, problems[0]))
            continue
        picked.append(item)
    return PickResult(wanted_code, quantity, tuple(picked), tuple(skipped))


def on_hand(
    shelf: Iterable[ShelfItem], now: datetime, settings: Settings | None = None
) -> dict[str, int]:
    """How many usable packages of each set are on the shelf."""
    rules = settings or Settings()
    counts: dict[str, int] = {}
    for item in shelf:
        if item.package.sterile(rules, now):
            counts[item.code] = counts.get(item.code, 0) + 1
    return counts


def oldest_first(shelf: Iterable[ShelfItem]) -> tuple[ShelfItem, ...]:
    return tuple(sorted(shelf, key=lambda item: (item.package.sterilized_at, item.asset)))
