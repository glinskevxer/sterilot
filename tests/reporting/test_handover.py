from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.cases.cart import CartLine, CaseCart
from sterilot.cases.issue import Issue
from sterilot.clock import Shift
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.quality.log import Duty, LogEntry
from sterilot.reporting import handover
from sterilot.settings import Settings
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2025, 8, 21)
AT = datetime(2025, 8, 21, 14, 45)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    made.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    yield made
    made.close()


def add_load(store: Store, reference: str, run: int, kind: ReleaseKind | None) -> None:
    cycle = SterilizerCycle(
        LotControlNumber("AC-1", DAY, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        datetime.combine(DAY, datetime.min.time()).replace(hour=8),
        "T-4471",
        CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    store.cycles.save(cycle)
    load = Load(
        reference,
        Method.STEAM_PREVAC,
        (LoadItem(f"ORT-{run:04d}", "ORT-MAJOR"),),
        "T-4471",
        cycle.started_at,
    )
    record = LoadRecord(load, cycle)
    if kind is not None:
        record = record.decided(ReleaseDecision(kind, ("waiting on the biological",), AT, "T-4471"))
    store.loads.save(record)


def test_a_quiet_shift_passes_nothing_on(store: Store) -> None:
    made = handover.build(store, AT)
    assert made.nothing_to_pass_on
    assert "nothing outstanding" in made.render()
    assert made.shift is Shift.FIRST


def test_the_shift_comes_from_the_clock(store: Store) -> None:
    assert handover.build(store, datetime(2025, 8, 21, 18, 0)).shift is Shift.SECOND
    assert handover.build(store, datetime(2025, 8, 22, 1, 0)).shift is Shift.THIRD


def test_a_load_nobody_decided_is_passed_on(store: Store) -> None:
    add_load(store, "LD-1", 1, None)
    made = handover.build(store, AT)
    assert [record.reference for record in made.undecided] == ["LD-1"]
    assert not made.nothing_to_pass_on
    assert "LD-1" in made.render()


def test_a_held_load_is_passed_on_with_its_reason(store: Store) -> None:
    add_load(store, "LD-2", 2, ReleaseKind.HELD)
    rendered = handover.build(store, AT).render()
    assert "waiting on the biological" in rendered


def test_a_released_load_is_not_passed_on(store: Store) -> None:
    add_load(store, "LD-3", 3, ReleaseKind.ROUTINE)
    made = handover.build(store, AT)
    assert made.undecided == ()
    assert made.held == ()


def test_a_chamber_that_ran_without_its_tests_owes_them(store: Store) -> None:
    add_load(store, "LD-1", 1, ReleaseKind.ROUTINE)
    made = handover.build(store, AT)
    assert [item.describe() for item in made.owed] == [
        "AC-1 still owes its air removal test",
        "AC-1 still owes its biological test",
    ]


def test_logging_the_tests_clears_the_debt(store: Store) -> None:
    add_load(store, "LD-1", 1, ReleaseKind.ROUTINE)
    for duty in (Duty.AIR_REMOVAL, Duty.BIOLOGICAL):
        store.duties.save(LogEntry(DAY, "AC-1", duty, True, "T-4471"))
    assert handover.build(store, AT).owed == ()


def test_carts_and_trays_are_counted(store: Store) -> None:
    store.carts.save(
        CaseCart.of("CC-991", "OR3-01", "PC-118", [CartLine("ORT-0114", "ORT-MAJOR")], "T-4471", AT)
    )
    store.issues.save(Issue("ORT-0115", "OR3-01", AT, "T-4471"))
    made = handover.build(store, AT)
    assert made.carts_waiting == 1
    assert made.trays_out == 1
    assert "carts waiting to go" in made.render()


def test_trays_out_alone_do_not_make_a_handover(store: Store) -> None:
    store.issues.save(Issue("ORT-0115", "OR3-01", AT, "T-4471"))
    made = handover.build(store, AT)
    assert made.nothing_to_pass_on
    assert "1 trays out to cases" in made.render()


def test_the_facility_name_comes_from_the_settings(store: Store) -> None:
    made = handover.build(store, AT, Settings(facility="Ridgeway CS"))
    assert made.render().startswith("Ridgeway CS handover")


def test_the_handover_belongs_to_the_processing_day(store: Store) -> None:
    made = handover.build(store, datetime(2025, 8, 22, 2, 0))
    assert made.day == date(2025, 8, 21)
