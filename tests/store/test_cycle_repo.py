from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import NotFoundError
from sterilot.ids import LotControlNumber
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store.cycle_repo import CycleStore, standard_spec
from sterilot.store.db import Database
from sterilot.store.migrations import migrate
from sterilot.units.duration import Duration
from sterilot.units.pressure import saturation_pressure
from sterilot.units.temperature import Temperature

DAY = date(2024, 12, 2)


def store() -> CycleStore:
    db = Database.in_memory()
    migrate(db)
    cycles = CycleStore(db)
    cycles.register_equipment("AC-1", "sterilizer", "Amsco 400", "Steris")
    cycles.register_equipment("AC-2", "sterilizer", "Amsco 400", "Steris")
    return cycles


def cycle(
    run: int = 1, day: date = DAY, equipment: str = "AC-1", **changes: object
) -> SterilizerCycle:
    values: dict[str, object] = {
        "lot": LotControlNumber(equipment, day, run),
        "spec": CycleSpec.standard(Method.STEAM_PREVAC),
        "started_at": datetime.combine(day, datetime.min.time()).replace(hour=7 + run),
        "operator": "T-4471",
        "measurements": CycleMeasurements(
            Temperature(133.4),
            Duration.of_minutes(4),
            Duration.of_minutes(31),
            saturation_pressure(Temperature(133.4)),
            4,
        ),
    }
    values.update(changes)
    return SterilizerCycle(**values)  # type: ignore[arg-type]


def test_a_cycle_round_trips_by_its_lot_number() -> None:
    cycles = store()
    cycles.save(cycle())
    found = cycles.get(LotControlNumber("AC-1", DAY, 1))
    assert found.equipment == "AC-1"
    assert found.operator == "T-4471"
    assert found.measurements.hold_temperature == Temperature(133.4)
    assert found.measurements.conditioning_pulses == 4
    cycles.db.close()


def test_the_lot_number_can_be_given_as_text() -> None:
    cycles = store()
    cycles.save(cycle())
    assert cycles.get("AC-1-20241202-01").run == 1
    cycles.db.close()


def test_the_pressure_survives_the_round_trip() -> None:
    cycles = store()
    cycles.save(cycle())
    found = cycles.get(LotControlNumber("AC-1", DAY, 1))
    assert found.measurements.chamber_pressure is not None
    assert found.measurements.chamber_pressure.kilopascals == pytest.approx(
        saturation_pressure(Temperature(133.4)).kilopascals
    )
    cycles.db.close()


def test_a_cycle_with_no_pressure_comes_back_without_one() -> None:
    cycles = store()
    cycles.save(cycle(measurements=CycleMeasurements(Temperature(133.0), Duration.of_minutes(4))))
    found = cycles.get(LotControlNumber("AC-1", DAY, 1))
    assert found.measurements.chamber_pressure is None
    assert found.measurements.conditioning_pulses is None
    cycles.db.close()


def test_an_unknown_lot_is_refused() -> None:
    cycles = store()
    with pytest.raises(NotFoundError):
        cycles.get(LotControlNumber("AC-1", DAY, 9))
    assert not cycles.exists(LotControlNumber("AC-1", DAY, 9))
    cycles.db.close()


def test_an_aborted_cycle_keeps_its_reason() -> None:
    cycles = store()
    cycles.save(cycle(aborted=True, abort_reason="door seal"))
    found = cycles.get(LotControlNumber("AC-1", DAY, 1))
    assert found.aborted
    assert found.abort_reason == "door seal"
    assert [item.run for item in cycles.aborted()] == [1]
    assert cycles.aborted("AC-2") == ()
    cycles.db.close()


def test_cycles_on_a_day_come_back_in_run_order() -> None:
    cycles = store()
    cycles.save(cycle(3))
    cycles.save(cycle(1))
    cycles.save(cycle(2))
    assert [item.run for item in cycles.on_day("ac 1", DAY)] == [1, 2, 3]
    cycles.db.close()


def test_the_next_run_number_follows_the_last() -> None:
    cycles = store()
    assert cycles.next_run("AC-1", DAY) == 1
    cycles.save(cycle(4))
    assert cycles.next_run("AC-1", DAY) == 5
    assert cycles.next_run("AC-2", DAY) == 1
    cycles.db.close()


def test_a_range_of_days_is_half_open() -> None:
    cycles = store()
    cycles.save(cycle(1, date(2024, 12, 1)))
    cycles.save(cycle(1, date(2024, 12, 2)))
    cycles.save(cycle(1, date(2024, 12, 3)))
    found = cycles.between("AC-1", date(2024, 12, 1), date(2024, 12, 3))
    assert [item.day for item in found] == [date(2024, 12, 1), date(2024, 12, 2)]
    cycles.db.close()


def test_the_default_resolver_keeps_the_stored_cycle_name() -> None:
    spec = standard_spec("HOUSE-PREVAC", Method.STEAM_PREVAC)
    assert spec.name == "HOUSE-PREVAC"
    assert spec.method is Method.STEAM_PREVAC
    assert standard_spec("PREVAC-132", Method.STEAM_PREVAC).name == "PREVAC-132"


def test_a_department_resolver_is_used_when_given() -> None:
    db = Database.in_memory()
    migrate(db)
    house = CycleSpec.standard(Method.STEAM_GRAVITY)
    cycles = CycleStore(db, lambda name, method: house)
    cycles.register_equipment("AC-1", "sterilizer", "Amsco", "Steris")
    cycles.save(cycle(measurements=CycleMeasurements(Temperature(122.0), Duration.of_minutes(30))))
    found = cycles.get(LotControlNumber("AC-1", DAY, 1))
    assert found.spec.method is Method.STEAM_GRAVITY
    db.close()


def test_saving_the_same_lot_again_replaces_it() -> None:
    cycles = store()
    cycles.save(cycle())
    cycles.save(cycle(operator="T-9002"))
    assert cycles.get(LotControlNumber("AC-1", DAY, 1)).operator == "T-9002"
    assert len(cycles.on_day("AC-1", DAY)) == 1
    cycles.db.close()
