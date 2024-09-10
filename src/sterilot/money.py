"""Money, in whole cents, because instrument repair is a real budget line.

Floats are not allowed anywhere near a currency amount. A repair quote of
$412.35 has to still be $412.35 after it has been summed with forty others and
split three ways across cost centres, and the only way to get that is to hold
integer cents and be explicit about how rounding is shared out.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sterilot.errors import ValidationError

_PATTERN = re.compile(
    r"^\s*(?P<sign>-)?\$?\s*(?P<whole>\d{1,3}(?:,\d{3})*|\d+)(?:\.(?P<cents>\d{1,2}))?\s*$"
)


@dataclass(frozen=True, order=True)
class Money:
    """An amount in whole cents. May be negative, because credits happen."""

    cents: int

    def __post_init__(self) -> None:
        if self.cents.__class__ is not int:
            raise ValidationError("money is held in whole cents", cents=self.cents)

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    @classmethod
    def of_dollars(cls, whole: int, cents: int = 0) -> Money:
        if not 0 <= cents < 100:
            raise ValidationError("cents run from nothing to ninety nine", cents=cents)
        sign = -1 if whole < 0 else 1
        return cls(whole * 100 + sign * cents)

    @classmethod
    def parse(cls, text: str) -> Money:
        """Read ``412.35``, ``$412.35``, ``1,204`` or ``-19.99``."""
        match = _PATTERN.match(text)
        if match is None:
            raise ValidationError("cannot read that as an amount", text=text)
        whole = int(match.group("whole").replace(",", ""))
        raw = match.group("cents") or "0"
        cents = int(raw.ljust(2, "0"))
        total = whole * 100 + cents
        return cls(-total if match.group("sign") else total)

    @property
    def dollars(self) -> int:
        return abs(self.cents) // 100 * (-1 if self.cents < 0 else 1)

    @property
    def negative(self) -> bool:
        return self.cents < 0

    def __add__(self, other: Money) -> Money:
        return Money(self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        return Money(self.cents - other.cents)

    def __neg__(self) -> Money:
        return Money(-self.cents)

    def __mul__(self, factor: int) -> Money:
        if factor.__class__ is not int:
            raise ValidationError("money is scaled by a whole number", factor=factor)
        return Money(self.cents * factor)

    def split(self, ways: int) -> tuple[Money, ...]:
        """Divide with the remainder given to the earliest shares, never lost."""
        if ways < 1:
            raise ValidationError("cannot split fewer than one way", ways=ways)
        base, remainder = divmod(abs(self.cents), ways)
        sign = -1 if self.cents < 0 else 1
        shares = [base + (1 if index < remainder else 0) for index in range(ways)]
        return tuple(Money(sign * share) for share in shares)

    def allocate(self, weights: Sequence[int]) -> tuple[Money, ...]:
        """Share out in proportion, with the remainder going by largest weight."""
        if not weights or any(weight < 0 for weight in weights):
            raise ValidationError("allocation weights are positive and present")
        total = sum(weights)
        if total == 0:
            raise ValidationError("allocation weights cannot all be zero")
        shares = [self.cents * weight // total for weight in weights]
        remainder = self.cents - sum(shares)
        order = sorted(range(len(weights)), key=lambda index: (-weights[index], index))
        step = 1 if remainder > 0 else -1
        for index in range(abs(remainder)):
            shares[order[index % len(order)]] += step
        return tuple(Money(share) for share in shares)

    def format(self) -> str:
        sign = "-" if self.cents < 0 else ""
        whole, cents = divmod(abs(self.cents), 100)
        return f"{sign}${whole:,}.{cents:02d}"

    def __str__(self) -> str:
        return self.format()


def total(amounts: Iterable[Money]) -> Money:
    return Money(sum(amount.cents for amount in amounts))
