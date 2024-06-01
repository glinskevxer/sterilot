"""Biological indicators, which are the only direct evidence of spore kill.

A vial of spores goes in the load, comes out, and gets incubated. Growth means
the cycle did not kill them. Nothing else in the department measures that
directly, which is why a positive biological outranks a printout full of
acceptable numbers.

Two things make a biological result easy to get wrong. It is not a result until
the incubation time has actually passed, and it means nothing without a control
vial from the same lot that was never in the chamber and did grow. A negative
control does not mean the cycle was wonderful, it means the spores were dead
before they went in and the test proved nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number, indicator_lot
from sterilot.interval import Window
from sterilot.methods import Method
from sterilot.units.duration import Duration


class Organism(Enum):
    """The spore on the strip, which is chosen for the method."""

    STEAROTHERMOPHILUS = "stearothermophilus"
    ATROPHAEUS = "atrophaeus"

    @property
    def label(self) -> str:
        return {
            "stearothermophilus": "Geobacillus stearothermophilus",
            "atrophaeus": "Bacillus atrophaeus",
        }[self.value]

    @property
    def methods(self) -> frozenset[Method]:
        if self is Organism.STEAROTHERMOPHILUS:
            return frozenset(
                {
                    Method.STEAM_PREVAC,
                    Method.STEAM_GRAVITY,
                    Method.STEAM_IUSS,
                    Method.HYDROGEN_PEROXIDE,
                }
            )
        return frozenset({Method.ETHYLENE_OXIDE})

    def challenges(self, method: Method) -> bool:
        return method in self.methods

    @classmethod
    def named(cls, value: str) -> Organism:
        wanted = value.strip().lower()
        for member in cls:
            if wanted in {member.value, member.label.lower()}:
                return member
        raise ValidationError("no such indicator organism", value=value)


class Readout(Enum):
    """How long the vial has to sit before anyone may look at it."""

    SUPER_RAPID = "super_rapid"
    RAPID = "rapid"
    CONVENTIONAL = "conventional"

    @property
    def minimum(self) -> Duration:
        return {
            "super_rapid": Duration.of_minutes(20),
            "rapid": Duration.of_hours(3),
            "conventional": Duration.of_hours(24),
        }[self.value]

    @property
    def maximum(self) -> Duration:
        return {
            "super_rapid": Duration.of_hours(4),
            "rapid": Duration.of_hours(24),
            "conventional": Duration.of_hours(48),
        }[self.value]

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def named(cls, value: str) -> Readout:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such readout type", value=value)


@dataclass(frozen=True)
class BiologicalIndicator:
    """A box of vials, as bought."""

    lot: str
    organism: Organism
    readout: Readout
    expires_on: date
    population_log: float = 6.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "lot", indicator_lot(self.lot))
        if self.population_log <= 0:
            raise ValidationError("a biological carries spores", lot=self.lot)

    def in_date_on(self, day: date) -> bool:
        return day <= self.expires_on

    def suits(self, method: Method) -> bool:
        return self.organism.challenges(method)


@dataclass(frozen=True)
class BiologicalResult:
    """One vial, incubated and read."""

    indicator: BiologicalIndicator
    started_at: datetime
    read_at: datetime
    positive: bool
    read_by: str
    is_control: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "read_by", badge_number(self.read_by))
        if self.read_at < self.started_at:
            raise ValidationError("a vial cannot be read before it is incubated")

    @property
    def incubated_for(self) -> Duration:
        return Duration((self.read_at - self.started_at).total_seconds())

    @property
    def window(self) -> Window:
        return Window(
            self.started_at + _delta(self.indicator.readout.minimum),
            self.started_at + _delta(self.indicator.readout.maximum),
        )

    @property
    def read_in_time(self) -> bool:
        """A vial read early is not a result, and one read late is stale."""
        return self.window.contains(self.read_at)

    @property
    def read_early(self) -> bool:
        return self.read_at < self.window.start

    def problems(self, method: Method, day: date) -> tuple[str, ...]:
        found: list[str] = []
        if not self.indicator.in_date_on(day):
            found.append(
                f"biological lot {self.indicator.lot} expired on {self.indicator.expires_on}"
            )
        if not self.indicator.suits(method):
            found.append(f"{self.indicator.organism.label} does not challenge {method.label}")
        if self.read_early:
            short = self.incubated_for.shortfall_against(self.indicator.readout.minimum)
            found.append(f"the vial was read {short.spelled()} early")
        elif not self.read_in_time:
            found.append(
                f"the vial was read after the {self.indicator.readout.label} window closed"
            )
        return tuple(found)

    def describe(self) -> str:
        kind = "control" if self.is_control else "test"
        verdict = "positive" if self.positive else "negative"
        return f"{kind} {self.indicator.lot} {verdict} after {self.incubated_for.spelled()}"

    def __str__(self) -> str:
        return self.describe()


def _delta(duration: Duration) -> datetime.timedelta:  # type: ignore[name-defined]
    from datetime import timedelta

    return timedelta(seconds=duration.seconds)


def verdict(
    test: BiologicalResult,
    control: BiologicalResult | None,
    method: Method,
    day: date,
) -> tuple[bool, tuple[str, ...]]:
    """Whether the biological passed, and everything wrong with the pair.

    The control has to come from the same lot, has to have grown, and has to be
    readable in its own right. Without one there is no result at all.
    """
    if test.is_control:
        raise ValidationError("that is a control, not a test vial", lot=test.indicator.lot)
    problems = list(test.problems(method, day))
    if control is None:
        problems.append("no control vial was incubated with this lot")
    else:
        if not control.is_control:
            raise ValidationError("that vial is not marked as a control", lot=control.indicator.lot)
        if control.indicator.lot != test.indicator.lot:
            problems.append(
                f"the control is lot {control.indicator.lot}, the test is {test.indicator.lot}"
            )
        if not control.read_in_time:
            problems.append("the control was not read inside its own window")
        elif not control.positive:
            problems.append("the control did not grow, so the test proves nothing")
    if test.positive:
        problems.append("the biological indicator grew")
    passed = not problems
    return passed, tuple(problems)
