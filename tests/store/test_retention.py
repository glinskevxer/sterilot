from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store import retention
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

TODAY = date(2025, 6, 18)
CUTOFF = date(2018, 6, 18)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    made.equipment.save_sterilizer(
        Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))
    )
    yield made
    made.close()


def add_load(store: Store, day: date, reference: str, released: bool = True) -> None:
    cycle = SterilizerCycle(
        LotControlNumber("AC-1", day, 1),
        CycleSpec.standard(Method.STEAM_PREVAC),
        datetime.combine(day, datetime.min.time()).replace(hour=8),
        "T-4471",
        CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    store.cycles.save(cycle)
    load = Load(
        reference,
        Method.STEAM_PREVAC,
        (LoadItem("ORT-0114", "ORT-MAJOR"),),
        "T-4471",
        cycle.started_at,
    )
    record = LoadRecord(load, cycle)
    if released:
        record = record.decided(
            ReleaseDecision(ReleaseKind.ROUTINE, (), cycle.started_at, "T-4471")
        )
    store.loads.save(record)


def test_the_cutoff_counts_back_from_today() -> None:
    assert retention.cutoff(TODAY, 7) == date(2018, 6, 18)


def test_a_short_retention_is_refused() -> None:
    with pytest.raises(ValidationError):
        retention.cutoff(TODAY, 2)


def test_an_empty_database_has_nothing_to_purge(store: Store) -> None:
    counted = retention.plan(store.db, CUTOFF)
    assert counted.empty
    assert "0 loads" in counted.describe()


def test_a_recent_load_is_not_in_the_plan(store: Store) -> None:
    add_load(store, date(2024, 1, 10), "LD-NEW")
    assert retention.plan(store.db, CUTOFF).empty


def test_an_old_released_load_is_in_the_plan(store: Store) -> None:
    add_load(store, date(2017, 1, 10), "LD-OLD")
    counted = retention.plan(store.db, CUTOFF)
    assert counted.loads == 1
    assert counted.cycles == 1
    assert not counted.empty


def test_an_old_undecided_load_is_kept(store: Store) -> None:
    add_load(store, date(2017, 1, 10), "LD-OPEN", released=False)
    counted = retention.plan(store.db, CUTOFF)
    assert counted.loads == 0
    assert counted.kept_open == 1
    assert counted.cycles == 0


def test_purging_removes_the_old_load_and_leaves_the_new_one(store: Store) -> None:
    add_load(store, date(2017, 1, 10), "LD-OLD")
    add_load(store, date(2024, 1, 10), "LD-NEW")
    retention.purge(store.db, CUTOFF)
    assert not store.loads.exists("LD-OLD")
    assert store.loads.exists("LD-NEW")
    assert store.db.scalar("SELECT count(*) FROM load_item") == 1


def test_purging_leaves_a_cycle_that_still_has_a_load(store: Store) -> None:
    add_load(store, date(2017, 1, 10), "LD-OPEN", released=False)
    retention.purge(store.db, CUTOFF)
    assert store.cycles.exists(LotControlNumber("AC-1", date(2017, 1, 10), 1))
    assert store.loads.exists("LD-OPEN")


def test_purging_never_touches_the_audit_trail(store: Store) -> None:
    from sterilot.quality.audit import Action

    store.quality.record(datetime(2017, 1, 10, 9, 0), "T-4471", Action.RECORDED, "load", "LD-OLD")
    add_load(store, date(2017, 1, 10), "LD-OLD")
    retention.purge(store.db, CUTOFF)
    assert len(store.quality.audit_trail().events) == 1
    assert store.quality.audit_trail().intact()


def test_purging_reports_what_it_took(store: Store) -> None:
    add_load(store, date(2017, 1, 10), "LD-OLD")
    counted = retention.purge(store.db, CUTOFF)
    assert counted.total == 2
    assert "1 loads" in counted.describe()


def test_purging_twice_takes_nothing_the_second_time(store: Store) -> None:
    add_load(store, date(2017, 1, 10), "LD-OLD")
    retention.purge(store.db, CUTOFF)
    assert retention.purge(store.db, CUTOFF).empty
