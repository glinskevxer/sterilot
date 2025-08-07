from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.cases.issue import Issue
from sterilot.decon.cycle import Phase, PhaseRecord, WasherCycle
from sterilot.decon.washer import Washer, WasherClass
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.quality.log import Duty, LogEntry
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.reporting import daily
from sterilot.settings import Settings
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2025, 2, 12)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    made.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    yield made
    made.close()


def cycle(run: int = 1, hour: int = 8) -> SterilizerCycle:
    return SterilizerCycle(
        LotControlNumber("AC-1", DAY, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        datetime.combine(DAY, datetime.min.time()).replace(hour=hour),
        "T-4471",
        CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
    )


def record(store: Store, reference: str, run: int, kind: ReleaseKind | None) -> None:
    made = cycle(run)
    store.cycles.save(made)
    load = Load(
        reference,
        Method.STEAM_PREVAC,
        (LoadItem(f"ORT-{run:04d}", "ORT-MAJOR"),),
        "T-4471",
        made.started_at,
    )
    item = LoadRecord(load, made)
    if kind is not None:
        item = item.decided(ReleaseDecision(kind, ("a reason",), made.started_at, "T-4471"))
    store.loads.save(item)


def logged(store: Store, duty: Duty) -> None:
    store.duties.save(LogEntry(DAY, "AC-1", duty, True, "T-4471"))


def test_a_quiet_day_reports_nothing_and_reads_clean(store: Store) -> None:
    report = daily.build(store, DAY)
    assert report.clean
    assert report.cycles == ()
    assert "nothing to report" in report.render()


def test_a_day_with_cycles_owes_its_daily_tests(store: Store) -> None:
    store.cycles.save(cycle())
    report = daily.build(store, DAY)
    assert not report.clean
    assert [gap.describe() for gap in report.gaps] == [
        "AC-1 has no air removal test",
        "AC-1 has no biological test",
    ]


def test_the_gaps_close_as_the_tests_are_logged(store: Store) -> None:
    store.cycles.save(cycle())
    logged(store, Duty.AIR_REMOVAL)
    logged(store, Duty.BIOLOGICAL)
    report = daily.build(store, DAY)
    assert report.gaps == ()
    assert report.clean


def test_a_chamber_that_did_not_run_owes_nothing(store: Store) -> None:
    report = daily.build(store, DAY)
    assert report.gaps == ()


def test_loads_are_split_by_what_was_decided(store: Store) -> None:
    logged(store, Duty.AIR_REMOVAL)
    logged(store, Duty.BIOLOGICAL)
    record(store, "LD-1", 1, ReleaseKind.ROUTINE)
    record(store, "LD-2", 2, ReleaseKind.HELD)
    record(store, "LD-3", 3, ReleaseKind.REJECTED)
    record(store, "LD-4", 4, None)
    report = daily.build(store, DAY)
    assert len(report.released) == 1
    assert len(report.held) == 1
    assert len(report.rejected) == 1
    assert len(report.loads) == 4
    assert not report.clean


def test_exceptions_raised_that_day_appear(store: Store) -> None:
    store.quality.save_exception(
        Nonconformance(
            "NC-1",
            Category.STERILIZATION,
            Severity.MINOR,
            datetime.combine(DAY, datetime.min.time()).replace(hour=9),
            "T-4471",
            "wet pack",
            subject="AC-1",
        )
    )
    report = daily.build(store, DAY)
    assert len(report.exceptions) == 1
    assert not report.clean
    assert "wet pack" in report.render()


def test_an_exception_from_another_day_does_not_appear(store: Store) -> None:
    store.quality.save_exception(
        Nonconformance(
            "NC-1",
            Category.STERILIZATION,
            Severity.MINOR,
            datetime(2025, 2, 11, 9, 0),
            "T-4471",
            "wet pack",
        )
    )
    assert daily.build(store, DAY).exceptions == ()


def test_the_facility_name_comes_from_the_settings(store: Store) -> None:
    report = daily.build(store, DAY, Settings(facility="Ridgeway CS"))
    assert report.render().startswith("Ridgeway CS daily report 2025-02-12")


def test_the_rendered_report_carries_every_section(store: Store) -> None:
    logged(store, Duty.AIR_REMOVAL)
    record(store, "LD-1", 1, ReleaseKind.ROUTINE)
    rendered = daily.build(store, DAY).render()
    assert "Cycles" in rendered
    assert "Loads" in rendered
    assert "Missing tests" in rendered
    assert "Exceptions" in rendered
    assert "AC-1-20250212-01" in rendered
    assert "biological" in rendered


def test_trays_out_are_counted(store: Store) -> None:
    store.issues.save(Issue("ORT-0114", "OR3-20250212-01", datetime(2025, 2, 12, 7, 0), "T-4471"))
    assert daily.build(store, DAY).trays_out == 1


def washer(store: Store) -> None:
    store.equipment.save_washer(
        Washer("WD-2", "Reliance 444", "Steris", WasherClass.SINGLE_CHAMBER)
    )


def wash_cycle(store: Store, day: date) -> None:
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


def test_a_washer_that_did_not_run_owes_no_cleaning_test(store: Store) -> None:
    washer(store)
    report = daily.build(store, DAY)
    assert report.gaps == ()
    assert report.clean


def test_a_washer_that_ran_owes_its_cleaning_test(store: Store) -> None:
    washer(store)
    wash_cycle(store, DAY)
    report = daily.build(store, DAY)
    assert [gap.describe() for gap in report.gaps] == ["WD-2 has no cleaning test"]


def test_the_washer_gap_closes_when_the_test_is_logged(store: Store) -> None:
    washer(store)
    wash_cycle(store, DAY)
    store.duties.save(LogEntry(DAY, "WD-2", Duty.CLEANING, True, "T-4471"))
    assert daily.build(store, DAY).gaps == ()


def test_an_ultrasonic_owes_nothing_even_when_it_runs(store: Store) -> None:
    store.equipment.save_washer(Washer("US-1", "Sonic", "Steris", WasherClass.ULTRASONIC))
    report = daily.build(store, DAY)
    assert report.gaps == ()
