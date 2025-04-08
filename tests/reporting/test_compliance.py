from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.quality.log import Duty, LogEntry
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.reporting import compliance
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.storage.shelf import Location, Zone
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

START = date(2025, 4, 1)
END = date(2025, 4, 8)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    made.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    yield made
    made.close()


def run_cycle(store: Store, day: date, run: int = 1) -> SterilizerCycle:
    cycle = SterilizerCycle(
        LotControlNumber("AC-1", day, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        datetime.combine(day, datetime.min.time()).replace(hour=8),
        "T-4471",
        CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    store.cycles.save(cycle)
    return cycle


def cover(store: Store, day: date) -> None:
    for duty in (Duty.AIR_REMOVAL, Duty.BIOLOGICAL):
        store.duties.save(LogEntry(day, "AC-1", duty, True, "T-4471"))


def test_an_empty_period_is_clean(store: Store) -> None:
    report = compliance.build(store, START, END)
    assert report.clean
    assert report.days == 7
    assert report.coverage == pytest.approx(1.0)
    assert "nothing to report" in report.render()


def test_a_day_run_without_its_tests_is_a_gap(store: Store) -> None:
    run_cycle(store, date(2025, 4, 2))
    report = compliance.build(store, START, END)
    assert not report.clean
    assert report.machines[0].days_run == 1
    assert report.machines[0].gaps == 1
    assert report.coverage == pytest.approx(0.0)


def test_covering_the_day_closes_the_gap(store: Store) -> None:
    run_cycle(store, date(2025, 4, 2))
    cover(store, date(2025, 4, 2))
    report = compliance.build(store, START, END)
    assert report.machines[0].gaps == 0
    assert report.clean
    assert report.machines[0].describe() == "AC-1 1 of 1 days covered"


def test_a_day_the_machine_did_not_run_owes_nothing(store: Store) -> None:
    report = compliance.build(store, START, END)
    assert report.machines[0].days_run == 0
    assert report.machines[0].rate == pytest.approx(1.0)


def test_loads_are_counted_by_status(store: Store) -> None:
    for index, kind in enumerate(
        (ReleaseKind.ROUTINE, ReleaseKind.HELD, ReleaseKind.REJECTED), start=1
    ):
        cycle = run_cycle(store, date(2025, 4, 3), index)
        load = Load(
            f"LD-{index}",
            Method.STEAM_PREVAC,
            (LoadItem(f"ORT-{index:04d}", "ORT-MAJOR"),),
            "T-4471",
            cycle.started_at,
        )
        record = LoadRecord(load, cycle).decided(
            ReleaseDecision(kind, (), cycle.started_at, "T-4471")
        )
        store.loads.save(record)
    report = compliance.build(store, START, END)
    assert report.total_loads == 3
    assert report.loads[LoadStatus.RELEASED] == 1
    assert report.loads[LoadStatus.HELD] == 1


def test_a_recalled_load_stops_the_period_reading_clean(store: Store) -> None:
    cycle = run_cycle(store, date(2025, 4, 3))
    cover(store, date(2025, 4, 3))
    load = Load(
        "LD-1",
        Method.STEAM_PREVAC,
        (LoadItem("ORT-0114", "ORT-MAJOR"),),
        "T-4471",
        cycle.started_at,
    )
    store.loads.save(
        LoadRecord(load, cycle).recalled(datetime(2025, 4, 4, 9, 0), "positive biological")
    )
    report = compliance.build(store, START, END)
    assert not report.clean
    assert report.loads[LoadStatus.RECALLED] == 1


def test_exceptions_are_counted_by_severity(store: Store) -> None:
    for index, severity in enumerate((Severity.MINOR, Severity.MAJOR), start=1):
        store.quality.save_exception(
            Nonconformance(
                f"NC-{index}",
                Category.STERILIZATION,
                severity,
                datetime(2025, 4, 2, 9, 0),
                "T-4471",
                "wet pack",
            )
        )
    report = compliance.build(store, START, END)
    assert report.exceptions[Severity.MINOR] == 1
    assert report.overdue_exceptions == 1
    assert not report.clean


def test_a_bad_storage_location_is_reported(store: Store) -> None:
    store.packages.save_location(
        Location("ST-B1", "under the sink", Zone.STERILE_STORE, 6, 10.0, 20.0, under_plumbing=True)
    )
    report = compliance.build(store, START, END)
    assert not report.clean
    assert any("under a sink" in item for item in report.storage_problems)


def test_a_lapsed_releaser_is_reported(store: Store) -> None:
    from sterilot.staff.tech import Role, Technician

    store.staff.save(Technician("T-4471", "R Ferreira", Role.TECHNICIAN))
    report = compliance.build(store, START, END)
    assert not report.clean
    assert "certification is not current" in report.lapsed_competencies[0]


def test_a_trainee_is_not_counted_as_a_lapsed_releaser(store: Store) -> None:
    from sterilot.staff.tech import Role, Technician

    store.staff.save(Technician("T-9100", "A Novak", Role.TRAINEE))
    report = compliance.build(store, START, END)
    assert report.lapsed_competencies == ()


def test_the_render_carries_every_section(store: Store) -> None:
    run_cycle(store, date(2025, 4, 2))
    rendered = compliance.build(store, START, END).render()
    assert "compliance 2025-04-01 to 2025-04-08" in rendered
    assert "Machines" in rendered
    assert "Loads" in rendered
    assert "daily test coverage" in rendered
