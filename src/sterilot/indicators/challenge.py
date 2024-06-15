"""Process challenge devices, and the daily air removal test.

A biological indicator loose in a chamber proves the chamber killed spores
sitting in open steam, which is not the question. The question is whether the
steam reached the middle of the hardest pack in the load, so the indicator goes
inside a device built to be at least as hard to get into as anything the load
contains.

The Bowie Dick test is the same idea aimed at a different failure. It is run
first thing, in an empty prevacuum chamber, and it fails when air is left
behind. Air left behind is what stops steam reaching the middle of a pack, so
the test is run before anything is loaded rather than after something is
ruined.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number, equipment_id, indicator_lot
from sterilot.methods import Method
from sterilot.sterilizer.equipment import Sterilizer

FAILURES_BEFORE_SERVICE = 2


class ChallengeKind(Enum):
    """What the pack is for."""

    AIR_REMOVAL = "air_removal"
    BIOLOGICAL = "biological"
    CHEMICAL = "chemical"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def runs_empty(self) -> bool:
        """Only the air removal test wants nothing else in the chamber."""
        return self is ChallengeKind.AIR_REMOVAL

    @classmethod
    def named(cls, value: str) -> ChallengeKind:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {"bowie_dick": cls.AIR_REMOVAL, "bd": cls.AIR_REMOVAL, "pcd": cls.BIOLOGICAL}
        for member in cls:
            if wanted == member.value:
                return member
        if wanted in aliases:
            return aliases[wanted]
        raise ValidationError("no such challenge kind", value=value)


@dataclass(frozen=True)
class ChallengePack:
    """A device the challenge goes inside."""

    kind: ChallengeKind
    description: str
    methods: frozenset[Method]
    lot: str = ""
    disposable: bool = True

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValidationError("a challenge pack needs a description")
        if not self.methods:
            raise ValidationError("a challenge pack is made for a method")
        if self.lot:
            object.__setattr__(self, "lot", indicator_lot(self.lot))
        if self.kind.runs_empty and any(not method.is_steam for method in self.methods):
            raise ValidationError("air removal is a steam test only")

    def suits(self, method: Method) -> bool:
        return method in self.methods


@dataclass(frozen=True)
class AirRemovalTest:
    """One Bowie Dick run."""

    equipment: str
    pack: ChallengePack
    at: datetime
    by: str
    passed: bool
    chamber_empty: bool = True
    first_run_of_day: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        object.__setattr__(self, "by", badge_number(self.by))
        if self.pack.kind is not ChallengeKind.AIR_REMOVAL:
            raise ValidationError("that pack is not an air removal test", equipment=self.equipment)

    @property
    def day(self) -> date:
        return self.at.date()

    def problems(self, sterilizer: Sterilizer) -> tuple[str, ...]:
        """Everything wrong with this test, given the chamber it ran in."""
        if sterilizer.equipment != self.equipment:
            raise ValidationError(
                "that test did not run in that chamber",
                test=self.equipment,
                sterilizer=sterilizer.equipment,
            )
        found: list[str] = []
        if not sterilizer.daily_air_removal_test:
            found.append("that chamber does not owe an air removal test")
        if not self.chamber_empty:
            found.append("the test ran with a load in the chamber")
        if not self.first_run_of_day:
            found.append("the test was not the first run of the day")
        if not self.passed:
            found.append("the air removal test failed")
        return tuple(found)

    def acceptable(self, sterilizer: Sterilizer) -> bool:
        return not self.problems(sterilizer)


def qualifies_for_the_day(
    tests: tuple[AirRemovalTest, ...], sterilizer: Sterilizer, day: date
) -> bool:
    """True when the chamber has a clean air removal test for ``day``.

    A chamber that owes no test qualifies with none at all, which is how the
    gravity sterilizer and both low temperature chambers get through the
    morning.
    """
    if not sterilizer.daily_air_removal_test:
        return True
    return any(
        test.day == day and test.equipment == sterilizer.equipment and test.acceptable(sterilizer)
        for test in tests
    )


def service_needed(tests: tuple[AirRemovalTest, ...], equipment: str) -> bool:
    """True once the run of failures at the end of the log reaches the limit."""
    wanted = equipment_id(equipment)
    run = 0
    for test in sorted(tests, key=lambda item: item.at):
        if test.equipment != wanted:
            continue
        run = run + 1 if not test.passed else 0
    return run >= FAILURES_BEFORE_SERVICE
