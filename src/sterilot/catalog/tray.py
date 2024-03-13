"""Count sheets: what is supposed to be in a set, and where.

A count sheet is the contract between the assembly bench and the operating
room. It is also the thing that decides which chamber the set can go in, and
that decision is not a property of the set, it is the intersection of every
item in it. One low temperature polymer retractor in an otherwise stainless
tray takes the whole tray out of the prevac sterilizer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sterilot.catalog.instrument import Instrument
from sterilot.errors import ValidationError
from sterilot.ids import catalog_number, tray_code
from sterilot.methods import Method
from sterilot.units.mass import Mass


@dataclass(frozen=True)
class CountLine:
    """One line of a count sheet."""

    instrument: Instrument
    quantity: int = 1
    position: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValidationError(
                "a count sheet line needs at least one of the item",
                catalog=self.instrument.catalog,
                quantity=self.quantity,
            )

    @property
    def catalog(self) -> str:
        return self.instrument.catalog

    @property
    def weight(self) -> Mass | None:
        if self.instrument.weight is None:
            return None
        return self.instrument.weight * self.quantity

    def describe(self) -> str:
        where = f" [{self.position}]" if self.position else ""
        optional = "" if self.required else " (optional)"
        return f"{self.quantity} x {self.instrument.label()}{where}{optional}"


@dataclass(frozen=True)
class CountSheet:
    """A named set and the items it holds."""

    code: str
    name: str
    lines: tuple[CountLine, ...]
    container: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", tray_code(self.code))
        if not self.name.strip():
            raise ValidationError("count sheet has no name", code=self.code)
        if not self.lines:
            raise ValidationError("count sheet has no lines", code=self.code)
        seen: set[str] = set()
        for line in self.lines:
            if line.catalog in seen:
                raise ValidationError(
                    "the same catalog number is on two lines",
                    code=self.code,
                    catalog=line.catalog,
                )
            seen.add(line.catalog)

    @classmethod
    def of(
        cls, code: str, name: str, lines: Iterable[CountLine], container: str | None = None
    ) -> CountSheet:
        return cls(code, name, tuple(lines), container)

    @property
    def item_count(self) -> int:
        """Every piece, counting quantities."""
        return sum(line.quantity for line in self.lines)

    @property
    def required_count(self) -> int:
        return sum(line.quantity for line in self.lines if line.required)

    def line_for(self, catalog: str) -> CountLine:
        wanted = catalog_number(catalog)
        for line in self.lines:
            if line.catalog == wanted:
                return line
        raise ValidationError(
            "that item is not on this count sheet", code=self.code, catalog=wanted
        )

    def holds(self, catalog: str) -> bool:
        try:
            self.line_for(catalog)
        except ValidationError:
            return False
        return True

    def instruments(self) -> tuple[Instrument, ...]:
        return tuple(line.instrument for line in self.lines)

    def methods(self) -> tuple[Method, ...]:
        """Methods every item on the sheet tolerates."""
        return tuple(
            method
            for method in Method
            if all(line.instrument.tolerates(method) for line in self.lines)
        )

    def refusals_for(self, method: Method) -> dict[str, str]:
        """Catalog number to reason, for every item that blocks ``method``."""
        found: dict[str, str] = {}
        for line in self.lines:
            reason = line.instrument.refusal_for(method)
            if reason is not None:
                found[line.catalog] = reason
        return found

    def tolerates(self, method: Method) -> bool:
        return not self.refusals_for(method)

    def known_weight(self) -> Mass:
        """Sum of the weights we have. Silent about the ones we do not."""
        total = Mass.zero()
        for line in self.lines:
            weight = line.weight
            if weight is not None:
                total = total + weight
        return total

    def weights_missing(self) -> tuple[str, ...]:
        return tuple(line.catalog for line in self.lines if line.instrument.weight is None)

    def sink_minutes(self) -> float:
        return sum(line.instrument.sink_minutes * line.quantity for line in self.lines)

    def lumened_items(self) -> tuple[Instrument, ...]:
        return tuple(line.instrument for line in self.lines if line.instrument.has_lumen)

    def label(self) -> str:
        return f"{self.code} {self.name}"

    def __str__(self) -> str:
        return self.label()
