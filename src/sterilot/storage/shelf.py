"""Sterile storage locations, and whether a shelf is allowed to be one.

Storage rules read like fussy carpentry and every one of them comes from a way
packages get contaminated. Off the floor, because floors get mopped and the
spray goes up. Away from the sprinkler head, because the wetting pattern needs
room and a wet pack is a lost pack. Off the outside wall, because that is where
condensation forms. Not under a sink, for reasons nobody should have to write
down.

A location that fails any of them is not a storage location, and the register
will say so rather than quietly holding trays somewhere it should not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import normalise_code, tray_code

FLOOR_CLEARANCE_CM = 25.0
SPRINKLER_CLEARANCE_CM = 45.0
OUTSIDE_WALL_CLEARANCE_CM = 5.0


class Zone(Enum):
    """How protected the space is."""

    STERILE_STORE = "sterile_store"
    SUBSTERILE = "substerile"
    THEATRE_CORE = "theatre_core"
    WARD = "ward"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def controlled(self) -> bool:
        """Temperature and humidity are held and traffic is restricted."""
        return self in {Zone.STERILE_STORE, Zone.THEATRE_CORE}

    @classmethod
    def named(cls, value: str) -> Zone:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such storage zone", value=value)


@dataclass(frozen=True)
class Location:
    """One shelf, rack or cabinet."""

    code: str
    description: str
    zone: Zone
    capacity_units: int
    floor_clearance_cm: float
    sprinkler_clearance_cm: float
    outside_wall_clearance_cm: float = 10.0
    closed_shelving: bool = True
    under_plumbing: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="location code"))
        if not self.description.strip():
            raise ValidationError("a location needs a description", code=self.code)
        if self.capacity_units < 1:
            raise ValidationError("a location holds something", code=self.code)
        for value, name in (
            (self.floor_clearance_cm, "floor clearance"),
            (self.sprinkler_clearance_cm, "sprinkler clearance"),
            (self.outside_wall_clearance_cm, "outside wall clearance"),
        ):
            if value < 0:
                raise ValidationError(f"{name} cannot be negative", code=self.code)

    def problems(self) -> tuple[str, ...]:
        """Every reason this shelf should not hold sterile packages."""
        found: list[str] = []
        if self.under_plumbing:
            found.append("the shelf is under a sink or a water line")
        if self.floor_clearance_cm < FLOOR_CLEARANCE_CM:
            found.append(
                f"the lowest shelf is {self.floor_clearance_cm:.0f} cm off the floor, "
                f"not {FLOOR_CLEARANCE_CM:.0f}"
            )
        if self.sprinkler_clearance_cm < SPRINKLER_CLEARANCE_CM:
            found.append(
                f"the top shelf is {self.sprinkler_clearance_cm:.0f} cm below the sprinkler, "
                f"not {SPRINKLER_CLEARANCE_CM:.0f}"
            )
        if self.outside_wall_clearance_cm < OUTSIDE_WALL_CLEARANCE_CM:
            found.append("the rack is against an outside wall")
        if not self.zone.controlled:
            found.append(f"{self.zone.label} is not a controlled area")
        return tuple(found)

    def usable(self) -> bool:
        return not self.problems()

    def label(self) -> str:
        return f"{self.code} {self.description}"

    def __str__(self) -> str:
        return self.label()


@dataclass(frozen=True)
class ParLevel:
    """How many of a set the department wants on the shelf."""

    code: str
    minimum: int
    target: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", tray_code(self.code))
        if self.minimum < 0:
            raise ValidationError("a par minimum cannot be negative", code=self.code)
        if self.target < self.minimum:
            raise ValidationError("a par target sits at or above the minimum", code=self.code)

    def shortfall(self, on_hand: int) -> int:
        """How many short of the target, which is what gets built next."""
        if on_hand < 0:
            raise ValidationError("a count cannot be negative", code=self.code)
        return max(self.target - on_hand, 0)

    def below_minimum(self, on_hand: int) -> bool:
        return on_hand < self.minimum


@dataclass(frozen=True)
class StorageMap:
    """The department's storage, with its par levels."""

    locations: tuple[Location, ...] = ()
    pars: tuple[ParLevel, ...] = ()

    def __post_init__(self) -> None:
        codes = [location.code for location in self.locations]
        if len(set(codes)) != len(codes):
            raise ConflictError("two locations share a code")
        sets = [par.code for par in self.pars]
        if len(set(sets)) != len(sets):
            raise ConflictError("two par levels cover the same set")

    def location(self, code: str) -> Location:
        wanted = normalise_code(code, field="location code")
        for location in self.locations:
            if location.code == wanted:
                return location
        raise NotFoundError("no such location", code=wanted)

    def par(self, code: str) -> ParLevel | None:
        wanted = tray_code(code)
        for par in self.pars:
            if par.code == wanted:
                return par
        return None

    def unusable(self) -> tuple[Location, ...]:
        return tuple(location for location in self.locations if not location.usable())

    def capacity(self) -> int:
        return sum(location.capacity_units for location in self.locations if location.usable())

    def build_list(self, on_hand: dict[str, int]) -> tuple[tuple[str, int], ...]:
        """What to build next, worst shortfall first."""
        wanted: list[tuple[str, int]] = []
        for par in self.pars:
            short = par.shortfall(on_hand.get(par.code, 0))
            if short:
                wanted.append((par.code, short))
        return tuple(sorted(wanted, key=lambda item: (-item[1], item[0])))
