"""Chemical indicators, which are six different things wearing one name.

A strip of tape on the outside of a pack turns dark when it has been near
steam. That is a class one, and all it says is that the pack is not still on
the shelf waiting to go in. Inside the pack a class five sits with the load and
reacts to all of the critical variables together, and it is what a technician
actually reads before handing the tray to the room.

Getting the class wrong is the common error, and it is invisible on the shelf
because every one of them is a strip of paper that changes colour. So the class
carries its own rules about where it may be used and what it is evidence of.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number, indicator_lot, normalise_code
from sterilot.methods import Method


class IndicatorClass(Enum):
    """The six classes, as the standard numbers them."""

    PROCESS = "1"
    SPECIFIC_TEST = "2"
    SINGLE_VARIABLE = "3"
    MULTI_VARIABLE = "4"
    INTEGRATING = "5"
    EMULATING = "6"

    @property
    def label(self) -> str:
        return {
            "1": "class 1 process indicator",
            "2": "class 2 specific test indicator",
            "3": "class 3 single variable",
            "4": "class 4 multi variable",
            "5": "class 5 integrating",
            "6": "class 6 emulating",
        }[self.value]

    @property
    def number(self) -> int:
        return int(self.value)

    @property
    def external_only(self) -> bool:
        """A process indicator says nothing about the inside of the pack."""
        return self is IndicatorClass.PROCESS

    @property
    def may_go_inside(self) -> bool:
        return self.number >= 3

    @property
    def cycle_specific(self) -> bool:
        """A class 6 is made for one cycle and is not evidence of another."""
        return self is IndicatorClass.EMULATING

    @property
    def stands_in_for_a_biological(self) -> bool:
        """Only the integrating class is correlated to spore kill."""
        return self.number >= 5

    @classmethod
    def numbered(cls, value: int | str) -> IndicatorClass:
        wanted = str(value).strip().lower().removeprefix("class").strip()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such indicator class", value=value)


class Placement(Enum):
    """Where the indicator was."""

    EXTERNAL = "external"
    INTERNAL = "internal"
    CHALLENGE_DEVICE = "challenge_device"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def named(cls, value: str) -> Placement:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such placement", value=value)


class Outcome(Enum):
    """What the strip looked like."""

    PASS = "pass"
    FAIL = "fail"
    UNREADABLE = "unreadable"

    @property
    def acceptable(self) -> bool:
        return self is Outcome.PASS

    @classmethod
    def named(cls, value: str) -> Outcome:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such outcome", value=value)


@dataclass(frozen=True)
class ChemicalIndicator:
    """A box of strips, as bought."""

    indicator_class: IndicatorClass
    lot: str
    expires_on: date
    methods: frozenset[Method]
    cycle_name: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "lot", indicator_lot(self.lot))
        if not self.methods:
            raise ValidationError("an indicator is made for a method", lot=self.lot)
        if self.indicator_class.cycle_specific and not self.cycle_name.strip():
            raise ValidationError("an emulating indicator names its cycle", lot=self.lot)
        if not self.indicator_class.cycle_specific and self.cycle_name.strip():
            raise ValidationError("only an emulating indicator is tied to one cycle", lot=self.lot)
        if self.cycle_name:
            object.__setattr__(
                self, "cycle_name", normalise_code(self.cycle_name, field="cycle name")
            )

    def in_date_on(self, day: date) -> bool:
        return day <= self.expires_on

    def suits(self, method: Method, cycle_name: str = "") -> bool:
        if method not in self.methods:
            return False
        if not self.indicator_class.cycle_specific:
            return True
        return (
            bool(cycle_name) and normalise_code(cycle_name, field="cycle name") == self.cycle_name
        )


@dataclass(frozen=True)
class ChemicalResult:
    """One strip, read by one person."""

    indicator: ChemicalIndicator
    placement: Placement
    outcome: Outcome
    read_at: datetime
    read_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "read_by", badge_number(self.read_by))
        if (
            self.placement is not Placement.EXTERNAL
            and self.indicator.indicator_class.external_only
        ):
            raise ValidationError(
                "a process indicator only goes on the outside",
                lot=self.indicator.lot,
                placement=self.placement.value,
            )

    @property
    def passed(self) -> bool:
        return self.outcome.acceptable

    def problems(self, method: Method, cycle_name: str, day: date) -> tuple[str, ...]:
        """Everything wrong with this reading, given the cycle it came out of."""
        found: list[str] = []
        if not self.indicator.in_date_on(day):
            found.append(
                f"indicator lot {self.indicator.lot} expired on {self.indicator.expires_on}"
            )
        if not self.indicator.suits(method, cycle_name):
            found.append(
                f"indicator lot {self.indicator.lot} is not made for {method.label}"
                if method not in self.indicator.methods
                else f"emulating indicator {self.indicator.lot} is for {self.indicator.cycle_name}"
            )
        if self.outcome is Outcome.UNREADABLE:
            found.append(f"the {self.placement.label} indicator could not be read")
        elif not self.passed:
            found.append(f"the {self.placement.label} indicator failed")
        return tuple(found)

    def describe(self) -> str:
        return f"{self.indicator.indicator_class.label} {self.placement.label} {self.outcome.value}"

    def __str__(self) -> str:
        return self.describe()
