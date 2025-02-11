from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import NotFoundError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store.cycle_repo import CycleStore
from sterilot.store.db import Database
from sterilot.store.load_repo import LoadStore
from sterilot.store.migrations import migrate
from sterilot.units.duration import Duration
from sterilot.units.mass import Mass
from sterilot.units.temperature import Temperature

DAY = date(2024, 12, 5)
BUILT = datetime(2024, 12, 5, 7, 30)


def stores() -> tuple[LoadStore, CycleStore]:
    db = Database.in_memory()
    migrate(db)
    cycles = CycleStore(db)
    cycles.register_equipment("AC-1", "sterilizer", "Amsco 400", "Steris")
    cycles.register_equipment("AC-2", "sterilizer", "Amsco 400", "Steris")
    return LoadStore(db, cycles), cycles


def cycle(run: int = 1, day: date = DAY, equipment: str = "AC-1") -> SterilizerCycle:
    return SterilizerCycle(
        LotControlNumber(equipment, day, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        datetime.combine(day, datetime.min.time()).replace(hour=8),
        "T-4471",
        CycleMeasurements(Temperature(133.0), Duration.of_minutes(4), Duration.of_minutes(31)),
    )


def record(
    reference: str = "LD-4412",
    assets: tuple[str, ...] = ("ORT-0114",),
    run: int = 1,
    day: date = DAY,
    equipment: str = "AC-1",
) -> LoadRecord:
    load = Load(
        reference,
        Method.STEAM_PREVAC,
        tuple(
            LoadItem(asset, "ORT-MAJOR", units=2, weight=Mass.of_grams(8000), implant=index == 0)
            for index, asset in enumerate(assets)
        ),
        "T-4471",
        BUILT,
    )
    return LoadRecord(load, cycle(run, day, equipment))


def test_a_load_round_trips_with_its_items() -> None:
    loads, cycles = stores()
    cycles.save(cycle())
    loads.save(record())
    found = loads.get("ld 4412")
    assert found.reference == "LD-4412"
    assert found.load.assets() == ("ORT-0114",)
    assert found.load.items[0].units == 2
    assert found.load.carries_implant
    assert found.status is LoadStatus.PENDING
    loads.db.close()


def test_the_cycle_comes_back_with_the_load() -> None:
    loads, cycles = stores()
    cycles.save(cycle())
    loads.save(record())
    found = loads.get("LD-4412")
    assert found.cycle.lot.format() == "AC-1-20241205-01"
    assert found.cycle.operator == "T-4471"
    loads.db.close()


def test_a_decision_round_trips_with_its_reasons() -> None:
    loads, cycles = stores()
    cycles.save(cycle())
    decision = ReleaseDecision(
        ReleaseKind.EMERGENCY, ("still cooling", "released early: trauma"), BUILT, "T-9002"
    )
    loads.save(record().decided(decision))
    found = loads.get("LD-4412")
    assert found.decision is not None
    assert found.decision.kind is ReleaseKind.EMERGENCY
    assert found.decision.reasons == ("still cooling", "released early: trauma")
    assert found.released
    loads.db.close()


def test_a_recall_round_trips() -> None:
    loads, cycles = stores()
    cycles.save(cycle())
    pulled = record().recalled(datetime(2024, 12, 8, 9, 0), "positive biological")
    loads.save(pulled)
    found = loads.get("LD-4412")
    assert found.status is LoadStatus.RECALLED
    assert found.recall_reason == "positive biological"
    loads.db.close()


def test_an_unknown_reference_is_refused() -> None:
    loads, _ = stores()
    with pytest.raises(NotFoundError):
        loads.get("LD-9999")
    assert not loads.exists("LD-9999")
    loads.db.close()


def test_saving_again_replaces_the_items() -> None:
    loads, cycles = stores()
    cycles.save(cycle())
    loads.save(record(assets=("ORT-0114", "ORT-0115")))
    loads.save(record(assets=("ORT-0116",)))
    found = loads.get("LD-4412")
    assert found.load.assets() == ("ORT-0116",)
    loads.db.close()


def test_loads_are_found_by_tray() -> None:
    loads, cycles = stores()
    cycles.save(cycle(1))
    cycles.save(cycle(2))
    loads.save(record("LD-1", ("ORT-0114",), run=1))
    loads.save(record("LD-2", ("ORT-0115",), run=2))
    assert [item.reference for item in loads.for_asset("ort 0114")] == ["LD-1"]
    assert loads.for_asset("XX-1") == ()
    loads.db.close()


def test_loads_are_found_by_lot_and_status() -> None:
    loads, cycles = stores()
    cycles.save(cycle(1))
    cycles.save(cycle(2))
    loads.save(record("LD-1", run=1))
    released = record("LD-2", run=2).decided(
        ReleaseDecision(ReleaseKind.ROUTINE, (), BUILT, "T-4471")
    )
    loads.save(released)
    assert [item.reference for item in loads.for_lot(LotControlNumber("AC-1", DAY, 2))] == ["LD-2"]
    assert [item.reference for item in loads.with_status(LoadStatus.PENDING)] == ["LD-1"]
    assert [item.reference for item in loads.with_status(LoadStatus.RELEASED)] == ["LD-2"]
    loads.db.close()


def test_a_window_of_build_times_is_half_open() -> None:
    loads, cycles = stores()
    cycles.save(cycle(1))
    loads.save(record("LD-1", run=1))
    assert len(loads.between(BUILT, datetime(2024, 12, 5, 8, 0))) == 1
    assert loads.between(datetime(2024, 12, 5, 8, 0), datetime(2024, 12, 6)) == ()
    loads.db.close()


def test_loads_are_found_by_chamber_and_day() -> None:
    loads, cycles = stores()
    cycles.save(cycle(1, DAY, "AC-1"))
    cycles.save(cycle(1, DAY, "AC-2"))
    cycles.save(cycle(1, date(2024, 12, 6), "AC-1"))
    loads.save(record("LD-1", run=1, equipment="AC-1"))
    loads.save(record("LD-2", run=1, equipment="AC-2"))
    loads.save(record("LD-3", run=1, day=date(2024, 12, 6), equipment="AC-1"))
    assert [item.reference for item in loads.on_equipment("AC-1")] == ["LD-1", "LD-3"]
    assert [item.reference for item in loads.on_equipment("AC-1", DAY)] == ["LD-1"]
    loads.db.close()


def test_the_weight_is_read_back_from_the_items() -> None:
    loads, cycles = stores()
    cycles.save(cycle())
    loads.save(record(assets=("ORT-0114", "ORT-0115")))
    assert loads.total_weight("LD-4412") == Mass.of_grams(16000)
    loads.db.close()


def test_loads_are_found_by_the_day_their_cycle_ran() -> None:
    loads, cycles = stores()
    cycles.save(cycle(1, DAY))
    cycles.save(cycle(1, date(2024, 12, 8)))
    loads.save(record("LD-1", run=1, day=DAY))
    loads.save(record("LD-2", run=1, day=date(2024, 12, 8)))
    found = loads.on_days(DAY, date(2024, 12, 8))
    assert [item.reference for item in found] == ["LD-1"]
    assert len(loads.on_days(DAY, date(2024, 12, 9))) == 2
    loads.db.close()
