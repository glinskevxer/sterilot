"""The queries the floor runs all day, and whether they use an index.

A department database is small by any normal standard and large by the standard
of a machine under a desk being asked a question while somebody waits at a
scanner. These tests assert on the query plan rather than on a stopwatch,
because a timing test on a build machine tells you about the build machine.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

from sterilot.assets.lifecycle import Stage
from sterilot.assets.tray import TrayInstance
from sterilot.cases.issue import Disposition, Issue
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

FIRST = date(2025, 1, 2)
LOADS = 300


@pytest.fixture(scope="module")
def loaded() -> Iterator[Store]:
    """A store with a few months of loads in it."""
    store = Store.in_memory()
    store.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    with store.db.transaction():
        for index in range(LOADS):
            day = FIRST + timedelta(days=index // 4)
            run = index % 4 + 1
            at = datetime.combine(day, datetime.min.time()).replace(hour=6 + run)
            cycle = SterilizerCycle(
                LotControlNumber("AC-1", day, run),
                CycleSpec.standard(Method.STEAM_PREVAC),
                at,
                "T-4471",
                CycleMeasurements(
                    Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)
                ),
            )
            store.cycles.save(cycle)
            asset = f"ORT-{index:04d}"
            load = Load(
                f"LD-{index:04d}",
                Method.STEAM_PREVAC,
                (LoadItem(asset, "ORT-MAJOR"),),
                "T-4471",
                at,
            )
            kind = ReleaseKind.HELD if index % 50 == 0 else ReleaseKind.ROUTINE
            store.loads.save(
                LoadRecord(load, cycle).decided(ReleaseDecision(kind, (), at, "T-4471"))
            )
            store.trays.save(TrayInstance.placed_in_service(asset, "ORT-MAJOR", at, "T-4471"))
    yield store
    store.close()


def plan(store: Store, sql: str, parameters: list[object]) -> str:
    rows = store.db.query(f"EXPLAIN QUERY PLAN {sql}", parameters)
    return " ".join(str(row["detail"]) for row in rows)


def test_the_fixture_really_is_that_size(loaded: Store) -> None:
    assert loaded.db.scalar("SELECT count(*) FROM load_record") == LOADS
    assert loaded.db.scalar("SELECT count(*) FROM sterilizer_cycle") == LOADS


def test_finding_a_load_by_reference_uses_the_primary_key(loaded: Store) -> None:
    detail = plan(loaded, "SELECT reference FROM load_record WHERE reference = ?", ["LD-0001"])
    assert "SCAN" not in detail


def test_finding_held_loads_uses_the_status_index(loaded: Store) -> None:
    detail = plan(
        loaded, "SELECT reference FROM load_record WHERE status = ?", [LoadStatus.HELD.value]
    )
    assert "load_by_status" in detail


def test_finding_a_load_by_tray_uses_the_asset_index(loaded: Store) -> None:
    detail = plan(loaded, "SELECT reference FROM load_item WHERE asset = ?", ["ORT-0007"])
    assert "load_item_by_asset" in detail


def test_a_chamber_day_uses_the_cycle_index(loaded: Store) -> None:
    detail = plan(
        loaded,
        "SELECT lot FROM sterilizer_cycle WHERE equipment_id = ? AND run_date = ?",
        ["AC-1", FIRST.isoformat()],
    )
    assert "sterilizer_cycle_by_day" in detail


def test_trays_of_a_set_use_the_code_index(loaded: Store) -> None:
    detail = plan(loaded, "SELECT asset FROM tray WHERE code = ?", ["ORT-MAJOR"])
    assert "tray_by_code" in detail


def test_open_issues_use_the_disposition_index(loaded: Store) -> None:
    detail = plan(loaded, "SELECT asset FROM issue WHERE disposition = ?", [Disposition.OPEN.value])
    assert "issue_by_disposition" in detail


def test_the_held_query_still_returns_the_right_loads(loaded: Store) -> None:
    held = loaded.loads.with_status(LoadStatus.HELD)
    assert len(held) == LOADS // 50
    assert all(record.status is LoadStatus.HELD for record in held)


def test_a_day_of_loads_comes_back_in_run_order(loaded: Store) -> None:
    found = loaded.loads.on_days(FIRST, FIRST + timedelta(days=1))
    assert [record.lot.run for record in found] == [1, 2, 3, 4]


def test_one_tray_finds_exactly_its_own_load(loaded: Store) -> None:
    found = loaded.loads.for_asset("ORT-0007")
    assert [record.reference for record in found] == ["LD-0007"]


def test_the_floor_board_counts_every_tray(loaded: Store) -> None:
    counts = loaded.trays.counts_by_stage()
    assert counts[Stage.SOILED] == LOADS


def test_an_issue_written_into_a_full_database_still_reads_back(loaded: Store) -> None:
    at = datetime(2025, 6, 1, 9, 0)
    loaded.issues.save(Issue("ORT-0007", "OR3-01", at, "T-4471"))
    try:
        assert len(loaded.issues.open_issues()) == 1
    finally:
        loaded.db.execute("DELETE FROM issue WHERE asset = ?", ["ORT-0007"])
