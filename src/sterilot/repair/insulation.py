"""Insulation testing for electrosurgical instruments.

A crack in the insulation of a laparoscopic instrument is invisible, is often
nowhere near the tip, and puts current into whatever the shaft is touching,
which the surgeon cannot see because it is outside the field of view. The only
way to find one is to run a tester over the whole working length at a voltage
high enough to arc through a defect.

So the rule is per reprocessing cycle rather than per year, the test voltage is
part of the record, and a defect anywhere on the shaft takes the instrument out
of service rather than downgrading it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.catalog.instrument import Instrument
from sterilot.errors import ValidationError
from sterilot.ids import asset_tag, badge_number, catalog_number, equipment_id

MINIMUM_TEST_VOLTAGE = 2000
STANDARD_TEST_VOLTAGE = 2500


@dataclass(frozen=True)
class InsulationTest:
    """One instrument, run over the tester."""

    asset: str
    catalog: str
    at: datetime
    by: str
    tester: str
    voltage: int
    passed: bool
    defect_at_cm: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "catalog", catalog_number(self.catalog))
        object.__setattr__(self, "by", badge_number(self.by))
        object.__setattr__(self, "tester", equipment_id(self.tester))
        if self.voltage <= 0:
            raise ValidationError("a test runs at a voltage", asset=self.asset)
        if self.passed and self.defect_at_cm is not None:
            raise ValidationError("a passing test found no defect", asset=self.asset)
        if not self.passed and self.defect_at_cm is None:
            raise ValidationError("a failing test records where the defect is", asset=self.asset)
        if self.defect_at_cm is not None and self.defect_at_cm < 0:
            raise ValidationError("a defect sits somewhere on the shaft", asset=self.asset)

    @property
    def day(self) -> date:
        return self.at.date()

    def problems(self, item: Instrument) -> tuple[str, ...]:
        """Everything wrong with this test, given the item it was run on."""
        if item.catalog != self.catalog:
            raise ValidationError(
                "that test is for a different item", test=self.catalog, item=item.catalog
            )
        found: list[str] = []
        if not item.insulated:
            found.append("that instrument has no insulation to test")
        if self.voltage < MINIMUM_TEST_VOLTAGE:
            found.append(f"the test ran at {self.voltage} V, below {MINIMUM_TEST_VOLTAGE}")
        if not self.passed:
            where = self.defect_at_cm
            assert where is not None
            found.append(f"insulation failed {where:.1f} cm from the tip")
        return tuple(found)

    def acceptable(self, item: Instrument) -> bool:
        return not self.problems(item)

    def describe(self) -> str:
        if self.passed:
            return f"{self.asset} passed at {self.voltage} V"
        where = self.defect_at_cm
        assert where is not None
        return f"{self.asset} failed at {self.voltage} V, defect {where:.1f} cm from the tip"

    def __str__(self) -> str:
        return self.describe()


@dataclass(frozen=True)
class InsulationLog:
    """Every insulation test, so the bench can see what is due."""

    tests: tuple[InsulationTest, ...] = ()

    @classmethod
    def of(cls, tests: Iterable[InsulationTest]) -> InsulationLog:
        return cls(tuple(sorted(tests, key=lambda item: item.at)))

    def with_test(self, test: InsulationTest) -> InsulationLog:
        return InsulationLog.of((*self.tests, test))

    def for_asset(self, asset: str) -> tuple[InsulationTest, ...]:
        wanted = asset_tag(asset)
        return tuple(item for item in self.tests if item.asset == wanted)

    def latest_for(self, asset: str) -> InsulationTest | None:
        found = self.for_asset(asset)
        return found[-1] if found else None

    def in_service(self, asset: str) -> bool:
        """An instrument is in service while its last test passed."""
        latest = self.latest_for(asset)
        return latest is not None and latest.passed

    def refusal(self, asset: str, item: Instrument, since: datetime) -> str | None:
        """Why this instrument may not go back in a tray, or None.

        ``since`` is when the instrument was last reprocessed. A test from
        before that does not cover this trip round the loop.
        """
        if not item.insulated:
            return None
        latest = self.latest_for(asset)
        if latest is None:
            return "the instrument has never been insulation tested"
        if not latest.passed:
            return latest.describe()
        if latest.at < since:
            return "the last insulation test predates the current reprocessing"
        return None

    def failures(self) -> tuple[InsulationTest, ...]:
        return tuple(item for item in self.tests if not item.passed)
