"""Building a load, which is a set of decisions made before anything runs.

A load is not a pile. Every item in it has to tolerate the method, the whole
thing has to fit the chamber, no single set may be over the weight that stops
it drying, and textiles go on the top shelf because condensate runs downward
and a wet pack under a linen pack is a linen pack's fault.

The implant rule is the one that decides other rules later. A load carrying an
implant cannot be released early, so the flag is set here at build time rather
than remembered at release time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sterilot.errors import ValidationError
from sterilot.ids import asset_tag, badge_number, normalise_code, tray_code
from sterilot.methods import Method
from sterilot.units.mass import SET_WEIGHT_LIMIT_KG, Mass


@dataclass(frozen=True)
class LoadItem:
    """One thing in the chamber."""

    asset: str
    code: str
    units: int = 1
    weight: Mass | None = None
    implant: bool = False
    textile: bool = False
    shelf: int = 1
    methods: frozenset[Method] = field(default_factory=lambda: frozenset(Method))

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "code", tray_code(self.code))
        if self.units < 1:
            raise ValidationError("an item takes at least one unit", asset=self.asset)
        if self.shelf < 1:
            raise ValidationError("shelves are numbered from the bottom", asset=self.asset)
        if not self.methods:
            raise ValidationError("an item tolerates at least one method", asset=self.asset)

    def tolerates(self, method: Method) -> bool:
        return method in self.methods

    @property
    def overweight_by(self) -> Mass:
        if self.weight is None:
            return Mass.zero()
        return self.weight.over(Mass(SET_WEIGHT_LIMIT_KG))


@dataclass(frozen=True)
class Load:
    """Everything that went into one chamber on one run."""

    reference: str
    method: Method
    items: tuple[LoadItem, ...]
    built_by: str
    built_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="load reference")
        )
        object.__setattr__(self, "built_by", badge_number(self.built_by))
        if not self.items:
            raise ValidationError("a load has something in it", reference=self.reference)
        seen: set[str] = set()
        for item in self.items:
            if item.asset in seen:
                raise ValidationError(
                    "the same tray is in the load twice",
                    reference=self.reference,
                    asset=item.asset,
                )
            seen.add(item.asset)

    @classmethod
    def of(
        cls,
        reference: str,
        method: Method,
        items: Iterable[LoadItem],
        built_by: str,
        built_at: datetime,
    ) -> Load:
        return cls(reference, method, tuple(items), built_by, built_at)

    @property
    def units(self) -> int:
        return sum(item.units for item in self.items)

    @property
    def carries_implant(self) -> bool:
        return any(item.implant for item in self.items)

    @property
    def carries_textiles(self) -> bool:
        return any(item.textile for item in self.items)

    def known_weight(self) -> Mass:
        total = Mass.zero()
        for item in self.items:
            if item.weight is not None:
                total = total + item.weight
        return total

    def assets(self) -> tuple[str, ...]:
        return tuple(item.asset for item in self.items)

    def item(self, asset: str) -> LoadItem:
        wanted = asset_tag(asset)
        for item in self.items:
            if item.asset == wanted:
                return item
        raise ValidationError(
            "that tray is not in this load", reference=self.reference, asset=wanted
        )

    def problems(self, capacity_units: int | None = None) -> tuple[str, ...]:
        """Everything wrong with the load as built."""
        found: list[str] = []
        for item in self.items:
            if not item.tolerates(self.method):
                found.append(f"{item.asset} does not tolerate {self.method.label}")
        if capacity_units is not None and self.units > capacity_units:
            found.append(f"the load is {self.units} units against a chamber of {capacity_units}")
        for item in self.items:
            over = item.overweight_by
            if over.kilograms > 0:
                found.append(f"{item.asset} is {over.format()} over the set weight limit")
        found.extend(self._arrangement_problems())
        if self.carries_implant and not self.method.may_be_stored:
            found.append("an implant cannot go through an immediate use cycle")
        return tuple(found)

    def _arrangement_problems(self) -> list[str]:
        if not self.carries_textiles:
            return []
        top = max(item.shelf for item in self.items)
        found: list[str] = []
        for item in self.items:
            if item.textile and item.shelf < top:
                found.append(f"{item.asset} is a textile pack below shelf {top}")
        return found

    def buildable(self, capacity_units: int | None = None) -> bool:
        return not self.problems(capacity_units)

    def label(self) -> str:
        return f"{self.reference} ({len(self.items)} items)"

    def __str__(self) -> str:
        return self.label()
