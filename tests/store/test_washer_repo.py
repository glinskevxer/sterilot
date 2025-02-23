from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.decon.cycle import Phase, PhaseRecord, PhaseSpec, Program, WasherCycle
from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import NotFoundError
from sterilot.store.store import Store
from sterilot.store.washer_repo import WasherStore
from sterilot.tolerance import Band
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

STARTED = datetime(2025, 2, 26, 6, 40)


@pytest.fixture
def washers() -> Iterator[WasherStore]:
    store = Store.in_memory()
    store.equipment.save_washer(
        Washer("WD-2", "Reliance 444", "Steris", WasherClass.SINGLE_CHAMBER)
    )
    yield store.washers
    store.close()


def program() -> Program:
    return Program.of(
        "instrument 2",
        [
            PhaseSpec(Phase.WASH, Duration.of_minutes(5), Band.at_least(55.0, "wash"), "enzymatic"),
            PhaseSpec(Phase.THERMAL, Duration.of_minutes(5), Band.at_least(90.0, "thermal")),
        ],
    )


def cycle(store: WasherStore, number: int = 318) -> WasherCycle:
    return WasherCycle(
        equipment="WD-2",
        program=store.program("INSTRUMENT-2"),
        number=number,
        started_at=STARTED,
        operator="T-4471",
        phases=(
            PhaseRecord(Phase.WASH, Duration.of_minutes(6), Temperature(60.0)),
            PhaseRecord(Phase.THERMAL, Duration.of_minutes(5), Temperature(91.0)),
        ),
    )


def test_a_program_round_trips(washers: WasherStore) -> None:
    washers.save_program(program())
    found = washers.program("instrument 2")
    assert found.name == "INSTRUMENT-2"
    assert len(found.phases) == 2
    assert found.a0_floor is not None
    spec = found.spec_for(Phase.WASH)
    assert spec is not None
    assert spec.detergent == "enzymatic"
    assert spec.temperature is not None
    assert spec.temperature.low == pytest.approx(55.0)


def test_a_phase_without_a_band_comes_back_without_one(washers: WasherStore) -> None:
    made = Program.of(
        "ultra 1",
        [PhaseSpec(Phase.WASH, Duration.of_minutes(5))],
        washer_class=WasherClass.ULTRASONIC,
        a0_floor=None,
    )
    washers.save_program(made)
    found = washers.program("ULTRA-1")
    assert found.a0_floor is None
    spec = found.spec_for(Phase.WASH)
    assert spec is not None
    assert spec.temperature is None


def test_saving_a_program_again_replaces_its_phases(washers: WasherStore) -> None:
    washers.save_program(program())
    washers.save_program(
        Program.of(
            "instrument 2",
            [
                PhaseSpec(Phase.WASH, Duration.of_minutes(9)),
                PhaseSpec(Phase.THERMAL, Duration.of_minutes(5)),
            ],
        )
    )
    found = washers.program("INSTRUMENT-2")
    spec = found.spec_for(Phase.WASH)
    assert spec is not None
    assert spec.minimum.minutes == pytest.approx(9.0)


def test_an_unknown_program_is_refused(washers: WasherStore) -> None:
    with pytest.raises(NotFoundError):
        washers.program("NOPE")


def test_the_standard_program_is_created_once(washers: WasherStore) -> None:
    first = washers.standard_program()
    second = washers.standard_program()
    assert first.name == second.name == "INSTRUMENT-1"
    assert len(washers.programs()) == 1


def test_a_cycle_round_trips_with_its_phases(washers: WasherStore) -> None:
    washers.save_program(program())
    washers.save_cycle(cycle(washers))
    found = washers.cycle("wd 2", STARTED, 318)
    assert found.operator == "T-4471"
    assert len(found.phases) == 2
    thermal = found.record_for(Phase.THERMAL)
    assert thermal is not None
    assert thermal.peak == Temperature(91.0)


def test_an_unknown_cycle_is_refused(washers: WasherStore) -> None:
    washers.save_program(program())
    with pytest.raises(NotFoundError):
        washers.cycle("WD-2", STARTED, 999)


def test_cycles_on_a_day_come_back_in_order(washers: WasherStore) -> None:
    washers.save_program(program())
    washers.save_cycle(cycle(washers, 318))
    washers.save_cycle(cycle(washers, 319))
    found = washers.on_day("WD-2", date(2025, 2, 26))
    assert [item.number for item in found] == [318, 319]
    assert washers.on_day("WD-2", date(2025, 2, 27)) == ()


def test_programs_are_listed_by_name(washers: WasherStore) -> None:
    washers.save_program(program())
    washers.standard_program()
    assert sorted(washers.programs()) == ["INSTRUMENT-1", "INSTRUMENT-2"]
