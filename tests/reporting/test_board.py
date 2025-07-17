from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.assets.lifecycle import Stage
from sterilot.assets.tray import TrayInstance
from sterilot.cases.cart import CartLine, CaseCart
from sterilot.cases.issue import Issue
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.reporting import board
from sterilot.settings import Settings
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.storage.shelf import ParLevel
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

NOW = datetime(2025, 7, 16, 10, 0)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    made.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    yield made
    made.close()


def tray(store: Store, asset: str, *stages: Stage) -> None:
    item = TrayInstance.placed_in_service(asset, "ORT-MAJOR", NOW, "T-4471")
    for stage in stages:
        item = item.moved_to(stage, NOW, "T-4471")
    store.trays.save(item)


def add_load(store: Store, reference: str, run: int, kind: ReleaseKind | None) -> None:
    cycle = SterilizerCycle(
        LotControlNumber("AC-1", date(2025, 7, 16), run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        NOW,
        "T-4471",
        CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    store.cycles.save(cycle)
    load = Load(reference, Method.STEAM_PREVAC, (LoadItem("ORT-0114", "ORT-MAJOR"),), "T-4471", NOW)
    record = LoadRecord(load, cycle)
    if kind is not None:
        record = record.decided(ReleaseDecision(kind, ("waiting",), NOW, "T-4471"))
    store.loads.save(record)


def test_a_quiet_department_reads_quiet(store: Store) -> None:
    made = board.build(store, NOW)
    assert made.quiet
    assert made.in_progress == 0
    assert "board 2025-07-16 10:00" in made.render()


def test_trays_in_the_loop_are_counted(store: Store) -> None:
    tray(store, "ORT-0114", Stage.DECONTAMINATION)
    tray(store, "ORT-0115")
    made = board.build(store, NOW)
    assert made.in_progress == 2
    assert made.stages[Stage.DECONTAMINATION] == 1
    assert not made.quiet


def test_a_sterile_tray_is_not_in_the_loop(store: Store) -> None:
    tray(
        store,
        "ORT-0114",
        Stage.DECONTAMINATION,
        Stage.CLEAN,
        Stage.ASSEMBLED,
        Stage.STERILIZING,
        Stage.COOLING,
        Stage.STERILE,
    )
    made = board.build(store, NOW)
    assert made.in_progress == 0
    assert made.stages[Stage.STERILE] == 1


def test_held_and_pending_loads_are_counted(store: Store) -> None:
    add_load(store, "LD-1", 1, ReleaseKind.HELD)
    add_load(store, "LD-2", 2, None)
    add_load(store, "LD-3", 3, ReleaseKind.ROUTINE)
    made = board.build(store, NOW)
    assert made.held == 1
    assert made.pending == 1


def test_trays_out_to_cases_are_counted(store: Store) -> None:
    store.issues.save(Issue("ORT-0114", "OR3-01", NOW, "T-4471"))
    assert board.build(store, NOW).out == 1


def test_carts_waiting_are_counted(store: Store) -> None:
    store.carts.save(
        CaseCart.of(
            "CC-991", "OR3-01", "PC-118", [CartLine("ORT-0114", "ORT-MAJOR")], "T-4471", NOW
        )
    )
    assert board.build(store, NOW).carts_waiting == 1


def test_the_build_list_appears_when_stock_is_short(store: Store) -> None:
    store.packages.save_par(ParLevel("ORT-MAJOR", 1, 2))
    made = board.build(store, NOW)
    assert made.to_build == (("ORT-MAJOR", 2),)
    assert "ORT-MAJOR" in made.render()
    assert not made.quiet


def test_the_facility_name_comes_from_the_settings(store: Store) -> None:
    made = board.build(store, NOW, Settings(facility="Ridgeway CS"))
    assert made.render().startswith("Ridgeway CS board")


def test_the_board_belongs_to_the_processing_day(store: Store) -> None:
    assert board.board_day(datetime(2025, 7, 17, 2, 0)) == date(2025, 7, 16)
    assert board.board_day(datetime(2025, 7, 17, 9, 0)) == date(2025, 7, 17)


def test_an_empty_board_prints_no_tables(store: Store) -> None:
    rendered = board.build(store, NOW).render()
    assert "stage" not in rendered
    assert "trays in the loop" in rendered
