"""Steam quality, which is the supply rather than the chamber.

A sterilizer can be in perfect order and still fail, because what arrives in
the pipe is not the steam the cycle assumes. Three things are measured and each
one is a different failure:

Non condensable gases are air and carbon dioxide carried in the steam. They
collect in the load and stop steam reaching it, and they are the reason a
chamber that passes its air removal test can still turn out an unsterile pack.

Dryness is how much of what arrives is vapour rather than water. Wet steam
carries less latent heat and soaks the packs on the way past, and a textile
load needs drier steam than a metal one because it holds what it is given.

Superheat measured at atmospheric expansion is steam that is too hot for its
pressure. It behaves like hot air, and the exposure time on the cycle card was
not worked out for hot air.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number, equipment_id
from sterilot.tolerance import Band

NON_CONDENSABLE_LIMIT = 3.5
SUPERHEAT_LIMIT_K = 25.0
DRYNESS_FLOOR_METAL = 0.90
DRYNESS_FLOOR_TEXTILE = 0.95


class LoadKind(Enum):
    """What the supply has to be good enough for."""

    METAL = "metal"
    TEXTILE = "textile"

    @property
    def dryness_floor(self) -> float:
        return DRYNESS_FLOOR_METAL if self is LoadKind.METAL else DRYNESS_FLOOR_TEXTILE

    @property
    def label(self) -> str:
        return self.value

    @classmethod
    def named(cls, value: str) -> LoadKind:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such load kind", value=value)


def non_condensable_band() -> Band:
    return Band.at_most(NON_CONDENSABLE_LIMIT, label="non condensable")


def superheat_band() -> Band:
    return Band.at_most(SUPERHEAT_LIMIT_K, label="superheat")


def dryness_band(kind: LoadKind) -> Band:
    return Band.at_least(kind.dryness_floor, label="dryness")


@dataclass(frozen=True)
class SteamQuality:
    """One steam quality test on one supply."""

    equipment: str
    at: datetime
    by: str
    non_condensable_percent: float
    dryness: float
    superheat_k: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        object.__setattr__(self, "by", badge_number(self.by))
        if self.non_condensable_percent < 0:
            raise ValidationError("a gas fraction cannot be negative", equipment=self.equipment)
        if not 0.0 < self.dryness <= 1.0:
            raise ValidationError("dryness is a fraction of one", dryness=self.dryness)
        if self.superheat_k < 0:
            raise ValidationError(
                "superheat measured at atmosphere is not negative", equipment=self.equipment
            )

    @property
    def day(self) -> date:
        return self.at.date()

    def readings(self, kind: LoadKind = LoadKind.TEXTILE) -> tuple[str, ...]:
        """Every reading explained, whether it passed or not."""
        return (
            non_condensable_band().evaluate(self.non_condensable_percent).explain(unit="percent"),
            dryness_band(kind).evaluate(self.dryness).explain(places=2),
            superheat_band().evaluate(self.superheat_k).explain(unit="K"),
        )

    def problems(self, kind: LoadKind = LoadKind.TEXTILE) -> tuple[str, ...]:
        """Everything the supply is not good enough for."""
        found: list[str] = []
        gas = non_condensable_band().evaluate(self.non_condensable_percent)
        if not gas.passed:
            found.append(gas.explain(unit="percent"))
        wetness = dryness_band(kind).evaluate(self.dryness)
        if not wetness.passed:
            found.append(wetness.explain(places=2))
        heat = superheat_band().evaluate(self.superheat_k)
        if not heat.passed:
            found.append(heat.explain(unit="K"))
        return tuple(found)

    def acceptable(self, kind: LoadKind = LoadKind.TEXTILE) -> bool:
        return not self.problems(kind)

    def good_for(self) -> tuple[LoadKind, ...]:
        """Which kinds of load this supply is good enough for."""
        return tuple(kind for kind in LoadKind if self.acceptable(kind))

    def describe(self) -> str:
        return (
            f"{self.equipment} {self.at:%Y-%m-%d}: "
            f"{self.non_condensable_percent:.1f} percent gas, "
            f"dryness {self.dryness:.2f}, superheat {self.superheat_k:.0f} K"
        )

    def __str__(self) -> str:
        return self.describe()
