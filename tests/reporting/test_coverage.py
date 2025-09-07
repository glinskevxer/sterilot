from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.decon.cycle import Phase, PhaseRecord, WasherCycle
from sterilot.decon.washer import Washer, WasherClass
from sterilot.ids import LotControlNumber
from sterilot.methods import Method
from sterilot.quality.log import Duty, LogEntry
from sterilot.reporting import coverage
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2025, 9, 8)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    made.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    made.equipment.save_washer(Washer("WD-2", "Reliance", "Steris", WasherClass.SINGLE_CHAMBER))
    yield made
    made.close()


def run_chamber(store: Store, day: date) -> None:
    store.cycles.save(
        SterilizerCycle(
            LotControlNumber("AC-1", day, 1),
            CycleSpec.standard(Method.STEAM_PREVAC),
            datetime.combine(day, datetime.min.time()).replace(hour=8),
            "T-4471",
            CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
        )
    )


def run_washer(store: Store, day: date) -> None:
    program = store.washers.standard_program()
    store.washers.save_cycle(
        WasherCycle(
            equipment="WD-2",
            program=program,
            number=1,
            started_at=datetime.combine(day, datetime.min.time()).replace(hour=6),
            operator="T-4471",
            phases=(PhaseRecord(Phase.WASH, Duration.of_minutes(6), Temperature(60.0)),),
        )
    )


def test_a_department_that_did_nothing_owes_nothing(store: Store) -> None:
    assert coverage.owed(store, DAY) == ()


def test_a_chamber_that_ran_owes_both_its_tests(store: Store) -> None:
    run_chamber(store, DAY)
    found = coverage.owed(store, DAY)
    assert [gap.duty for gap in found] == [Duty.AIR_REMOVAL, Duty.BIOLOGICAL]
    assert found[0].describe() == "AC-1 has no air removal test"


def test_a_washer_that_ran_owes_its_cleaning_test(store: Store) -> None:
    run_washer(store, DAY)
    found = coverage.owed(store, DAY)
    assert [gap.equipment for gap in found] == ["WD-2"]
    assert found[0].kind == "washer"


def test_logging_a_test_closes_its_gap(store: Store) -> None:
    run_chamber(store, DAY)
    store.duties.save(LogEntry(DAY, "AC-1", Duty.AIR_REMOVAL, True, "T-4471"))
    assert [gap.duty for gap in coverage.owed(store, DAY)] == [Duty.BIOLOGICAL]


def test_a_failed_test_does_not_close_a_gap(store: Store) -> None:
    run_chamber(store, DAY)
    store.duties.save(LogEntry(DAY, "AC-1", Duty.AIR_REMOVAL, False, "T-4471", "uneven"))
    assert len(coverage.owed(store, DAY)) == 2


def test_ran_on_answers_for_both_kinds(store: Store) -> None:
    run_chamber(store, DAY)
    assert coverage.ran_on(store, "AC-1", "sterilizer", DAY)
    assert not coverage.ran_on(store, "WD-2", "washer", DAY)
    run_washer(store, DAY)
    assert coverage.ran_on(store, "WD-2", "washer", DAY)


def test_days_run_and_covered_count_the_same_days(store: Store) -> None:
    days = (DAY, date(2025, 9, 9))
    run_chamber(store, DAY)
    duties = frozenset({Duty.AIR_REMOVAL, Duty.BIOLOGICAL})
    assert coverage.days_run(store, "AC-1", "sterilizer", days) == 1
    assert coverage.days_covered(store, "AC-1", "sterilizer", duties, days) == 0
    for duty in duties:
        store.duties.save(LogEntry(DAY, "AC-1", duty, True, "T-4471"))
    assert coverage.days_covered(store, "AC-1", "sterilizer", duties, days) == 1
