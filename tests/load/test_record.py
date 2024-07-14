from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadRegister, LoadStatus
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2024, 7, 15)
START = datetime(2024, 7, 15, 8, 0)


def cycle(run: int = 1, method: Method = Method.STEAM_PREVAC, day: date = DAY) -> SterilizerCycle:
    return SterilizerCycle(
        LotControlNumber("AC-1", day, run),
        CycleSpec.standard(method),
        datetime.combine(day, START.time()),
        "T-4471",
        CycleMeasurements(
            Temperature(133.0),
            Duration.of_minutes(4),
            Duration.of_minutes(31) if method is not Method.STEAM_IUSS else Duration.zero(),
        ),
    )


def load(
    reference: str = "LD-4412",
    assets: tuple[str, ...] = ("ORT-0114",),
    method: Method = Method.STEAM_PREVAC,
) -> Load:
    return Load(
        reference,
        method,
        tuple(LoadItem(asset, "ORT-MAJOR") for asset in assets),
        "T-4471",
        START,
    )


def released(kind: ReleaseKind = ReleaseKind.ROUTINE) -> ReleaseDecision:
    return ReleaseDecision(kind, (), datetime(2024, 7, 15, 10, 0), "T-4471")


def test_a_load_and_cycle_have_to_agree_on_the_method() -> None:
    with pytest.raises(ValidationError):
        LoadRecord(load(method=Method.STEAM_IUSS), cycle())


def test_a_recall_records_why() -> None:
    with pytest.raises(ValidationError):
        LoadRecord(load(), cycle(), recalled_at=datetime(2024, 7, 16, 9, 0))


def test_a_new_record_is_pending() -> None:
    record = LoadRecord(load(), cycle())
    assert record.status is LoadStatus.PENDING
    assert not record.released
    assert record.summary() == "LD-4412 AC-1-20240715-01 pending"


def test_a_decision_moves_the_status() -> None:
    record = LoadRecord(load(), cycle()).decided(released())
    assert record.status is LoadStatus.RELEASED
    assert record.released
    assert LoadStatus.RELEASED.contents_usable


def test_a_held_load_is_not_released() -> None:
    held = ReleaseDecision(ReleaseKind.HELD, ("waiting on the biological",), START, "T-4471")
    record = LoadRecord(load(), cycle()).decided(held)
    assert record.status is LoadStatus.HELD
    assert not record.released


def test_a_rejected_load_reads_as_rejected() -> None:
    rejected = ReleaseDecision(ReleaseKind.REJECTED, ("cold chamber",), START, "T-4471")
    assert LoadRecord(load(), cycle()).decided(rejected).status is LoadStatus.REJECTED


def test_a_recall_outranks_the_decision() -> None:
    record = LoadRecord(load(), cycle()).decided(released())
    recalled = record.recalled(datetime(2024, 7, 18, 9, 0), "positive biological on AC-1")
    assert recalled.status is LoadStatus.RECALLED
    assert not recalled.released


def test_a_recalled_load_cannot_be_decided_again() -> None:
    record = LoadRecord(load(), cycle()).recalled(
        datetime(2024, 7, 18, 9, 0), "positive biological"
    )
    with pytest.raises(ConflictError):
        record.decided(released())
    with pytest.raises(ConflictError):
        record.recalled(datetime(2024, 7, 19, 9, 0), "again")


def test_holds_finds_a_tray_by_normalised_tag() -> None:
    record = LoadRecord(load(assets=("ORT-0114", "GEN-0207")), cycle())
    assert record.holds("ort 0114")
    assert not record.holds("XX-1")


def test_the_register_refuses_a_duplicate_reference() -> None:
    register = LoadRegister.of([LoadRecord(load(), cycle())])
    with pytest.raises(ConflictError):
        register.with_record(LoadRecord(load(), cycle(run=2)))


def test_the_register_finds_by_reference() -> None:
    register = LoadRegister.of([LoadRecord(load(), cycle())])
    assert register.get("ld 4412").reference == "LD-4412"
    with pytest.raises(NotFoundError):
        register.get("LD-9999")


def test_replacing_swaps_one_record() -> None:
    register = LoadRegister.of([LoadRecord(load(), cycle()), LoadRecord(load("LD-4413"), cycle(2))])
    updated = register.get("LD-4412").decided(released())
    register = register.replacing(updated)
    assert register.get("LD-4412").released
    assert not register.get("LD-4413").released


def test_replacing_a_record_that_is_not_there_is_refused() -> None:
    with pytest.raises(NotFoundError):
        LoadRegister().replacing(LoadRecord(load(), cycle()))


def test_the_register_finds_by_lot_and_by_tray() -> None:
    first = LoadRecord(load("LD-1", ("ORT-0114",)), cycle(1))
    second = LoadRecord(load("LD-2", ("GEN-0207",)), cycle(2))
    register = LoadRegister.of([first, second])
    assert [item.reference for item in register.for_lot(LotControlNumber("AC-1", DAY, 2))] == [
        "LD-2"
    ]
    assert [item.reference for item in register.for_asset("ort 0114")] == ["LD-1"]


def test_the_register_filters_by_chamber_and_day() -> None:
    first = LoadRecord(load("LD-1"), cycle(1))
    later = LoadRecord(load("LD-2"), cycle(1, day=date(2024, 7, 16)))
    register = LoadRegister.of([later, first])
    assert [item.reference for item in register.on_equipment("AC-1")] == ["LD-1", "LD-2"]
    assert [item.reference for item in register.on_equipment("AC-1", DAY)] == ["LD-1"]
    assert register.on_equipment("AC-2") == ()


def test_the_register_lists_by_status() -> None:
    first = LoadRecord(load("LD-1"), cycle(1)).decided(released())
    second = LoadRecord(load("LD-2"), cycle(2))
    register = LoadRegister.of([first, second])
    assert [item.reference for item in register.with_status(LoadStatus.RELEASED)] == ["LD-1"]
    assert [item.reference for item in register.undecided()] == ["LD-2"]
