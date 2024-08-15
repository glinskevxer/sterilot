"""Case carts: the card turned into actual trays on actual shelves.

A cart is checked against the card it was built from, and the interesting part
is that not every gap is the same size. A missing essential set stops the case
and somebody has to be told now. A missing preferred set is a note on the cart.
An extra tray nobody asked for is worth knowing about too, because it will come
back soiled and be reprocessed for no reason.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sterilot.cases.preference_card import PreferenceCard
from sterilot.errors import ValidationError
from sterilot.ids import asset_tag, badge_number, case_number, normalise_code, tray_code


@dataclass(frozen=True)
class CartLine:
    """One tray on the cart."""

    asset: str
    code: str
    location: str = ""
    picked_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "code", tray_code(self.code))
        if self.location:
            object.__setattr__(
                self, "location", normalise_code(self.location, field="location code")
            )
        if self.picked_by:
            object.__setattr__(self, "picked_by", badge_number(self.picked_by))


@dataclass(frozen=True)
class Gap:
    """A difference between the cart and the card."""

    code: str
    wanted: int
    on_cart: int
    essential: bool

    @property
    def short(self) -> int:
        return max(self.wanted - self.on_cart, 0)

    @property
    def blocking(self) -> bool:
        return self.essential and self.short > 0

    def describe(self) -> str:
        if self.wanted == 0:
            return f"{self.code} is on the cart and not on the card"
        weight = "essential" if self.essential else "preferred"
        return f"{self.code} short {self.short} of {self.wanted} ({weight})"


@dataclass(frozen=True)
class CaseCart:
    """One cart, for one case."""

    reference: str
    case: str
    card_reference: str
    lines: tuple[CartLine, ...]
    built_by: str
    built_at: datetime
    delivered_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="cart reference")
        )
        object.__setattr__(self, "case", case_number(self.case))
        object.__setattr__(
            self, "card_reference", normalise_code(self.card_reference, field="card reference")
        )
        object.__setattr__(self, "built_by", badge_number(self.built_by))
        assets = [line.asset for line in self.lines]
        if len(set(assets)) != len(assets):
            raise ValidationError("the same tray is on the cart twice", reference=self.reference)
        if self.delivered_at is not None and self.delivered_at < self.built_at:
            raise ValidationError(
                "a cart cannot be delivered before it is built", reference=self.reference
            )

    @classmethod
    def of(
        cls,
        reference: str,
        case: str,
        card_reference: str,
        lines: Iterable[CartLine],
        built_by: str,
        built_at: datetime,
        delivered_at: datetime | None = None,
    ) -> CaseCart:
        return cls(reference, case, card_reference, tuple(lines), built_by, built_at, delivered_at)

    @property
    def delivered(self) -> bool:
        return self.delivered_at is not None

    def counts(self) -> dict[str, int]:
        found: dict[str, int] = {}
        for line in self.lines:
            found[line.code] = found.get(line.code, 0) + 1
        return found

    def assets(self) -> tuple[str, ...]:
        return tuple(line.asset for line in self.lines)

    def gaps(self, card: PreferenceCard) -> tuple[Gap, ...]:
        """Every difference between this cart and its card."""
        if card.reference != self.card_reference:
            raise ValidationError(
                "that card is not the one this cart was built from",
                cart=self.reference,
                card=card.reference,
            )
        on_cart = self.counts()
        found: list[Gap] = []
        for line in card.lines:
            have = on_cart.get(line.code, 0)
            if have < line.quantity:
                found.append(Gap(line.code, line.quantity, have, line.essential))
        for code in sorted(on_cart):
            if not card.calls_for(code):
                found.append(Gap(code, 0, on_cart[code], False))
        return tuple(found)

    def blocking_gaps(self, card: PreferenceCard) -> tuple[Gap, ...]:
        return tuple(gap for gap in self.gaps(card) if gap.blocking)

    def ready(self, card: PreferenceCard) -> bool:
        return not self.blocking_gaps(card)

    def summary(self, card: PreferenceCard) -> str:
        gaps = self.gaps(card)
        if not gaps:
            return f"{self.reference} matches {card.reference}"
        return f"{self.reference}: " + "; ".join(gap.describe() for gap in gaps)

    def delivered_on(self, at: datetime) -> CaseCart:
        if self.delivered:
            raise ValidationError("that cart was already delivered", reference=self.reference)
        return CaseCart(
            self.reference,
            self.case,
            self.card_reference,
            self.lines,
            self.built_by,
            self.built_at,
            at,
        )
