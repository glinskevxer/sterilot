from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadRegister
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.recall.scope import (
    QualificationEvent,
    Trigger,
    last_pass_before,
    scope_for,
)
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2024, 8, 5)


def at(hour: int, day: date = DAY) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(hour=hour)


def record(
    reference: str,
    run: int,
    hour: int,
    asset: str = "ORT-0114",
    equipment: str = "AC-1",
    day: date = DAY,
    released: bool = True,
) -> LoadRecord:
    cycle = SterilizerCycle(
        LotControlNumber(equipment, day, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        at(hour, day),
        "T-4471",
        CycleMeasurements(Temperature(133.0), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    load = Load(
        reference, Method.STEAM_PREVAC, (LoadItem(asset, "ORT-MAJOR"),), "T-4471", at(hour, day)
    )
    made = LoadRecord(load, cycle)
    if released:
        made = made.decided(ReleaseDecision(ReleaseKind.ROUTINE, (), at(hour, day), "T-4471"))
    return made


def event(
    hour: int,
    passed: bool,
    kind: Trigger = Trigger.BIOLOGICAL,
    equipment: str = "AC-1",
    day: date = DAY,
) -> QualificationEvent:
    return QualificationEvent(equipment, kind, at(hour, day), passed)


def test_trigger_lookup() -> None:
    assert Trigger.named("bowie dick") is Trigger.AIR_REMOVAL
    assert Trigger.named("BI") is Trigger.BIOLOGICAL
    assert Trigger.AIR_REMOVAL.label == "air removal"
    with pytest.raises(ValidationError):
        Trigger.named("guesswork")


def test_last_pass_ignores_other_chambers_and_other_kinds() -> None:
    events = (
        event(6, True),
        event(7, True, equipment="AC-2"),
        event(8, True, kind=Trigger.AIR_REMOVAL),
    )
    found = last_pass_before(events, "AC-1", Trigger.BIOLOGICAL, at(12))
    assert found is not None
    assert found.at == at(6)


def test_last_pass_ignores_failures_and_later_events() -> None:
    events = (event(6, True), event(9, False), event(14, True))
    found = last_pass_before(events, "AC-1", Trigger.BIOLOGICAL, at(12))
    assert found is not None
    assert found.at == at(6)


def test_a_passing_test_opens_no_recall() -> None:
    with pytest.raises(ValidationError):
        scope_for(LoadRegister(), (), event(12, True))


def test_the_recall_runs_back_to_the_last_passing_test() -> None:
    register = LoadRegister.of([record("LD-1", 1, 5), record("LD-2", 2, 8), record("LD-3", 3, 11)])
    events = (event(7, True), event(12, False))
    scope = scope_for(register, events, event(12, False))
    assert scope.anchored
    assert [item.reference for item in scope.loads] == ["LD-2", "LD-3"]
    assert scope.window.start == at(7)


def test_loads_before_the_last_pass_are_left_alone() -> None:
    register = LoadRegister.of([record("LD-1", 1, 5)])
    scope = scope_for(register, (event(7, True),), event(12, False))
    assert scope.loads == ()
    assert scope.load_count == 0


def test_with_no_earlier_pass_the_recall_opens_at_the_first_record() -> None:
    register = LoadRegister.of([record("LD-1", 1, 5), record("LD-2", 2, 8)])
    scope = scope_for(register, (), event(12, False))
    assert not scope.anchored
    assert [item.reference for item in scope.loads] == ["LD-1", "LD-2"]


def test_a_chamber_with_no_loads_gets_an_empty_recall() -> None:
    scope = scope_for(LoadRegister(), (), event(12, False))
    assert scope.loads == ()
    assert scope.window.start == scope.window.end


def test_a_load_started_exactly_at_the_failure_is_caught() -> None:
    register = LoadRegister.of([record("LD-1", 1, 12)])
    scope = scope_for(register, (event(7, True),), event(12, False))
    assert [item.reference for item in scope.loads] == ["LD-1"]


def test_loads_on_another_chamber_are_not_caught() -> None:
    register = LoadRegister.of([record("LD-1", 1, 8, equipment="AC-2")])
    scope = scope_for(register, (event(7, True),), event(12, False))
    assert scope.loads == ()


def test_the_scope_lists_the_trays_once_each() -> None:
    register = LoadRegister.of(
        [record("LD-1", 1, 8, asset="ORT-0114"), record("LD-2", 2, 9, asset="ORT-0114")]
    )
    scope = scope_for(register, (event(7, True),), event(12, False))
    assert scope.assets() == ("ORT-0114",)


def test_the_scope_separates_the_released_loads() -> None:
    register = LoadRegister.of([record("LD-1", 1, 8), record("LD-2", 2, 9, released=False)])
    scope = scope_for(register, (event(7, True),), event(12, False))
    assert [item.reference for item in scope.released_loads()] == ["LD-1"]


def test_an_air_removal_failure_uses_its_own_history() -> None:
    register = LoadRegister.of([record("LD-1", 1, 8)])
    events = (event(7, True, kind=Trigger.BIOLOGICAL),)
    scope = scope_for(register, events, event(12, False, kind=Trigger.AIR_REMOVAL))
    assert not scope.anchored
    assert scope.kind is Trigger.AIR_REMOVAL


def test_the_summary_reads_like_a_notice_heading() -> None:
    register = LoadRegister.of([record("LD-1", 1, 8)])
    scope = scope_for(register, (event(7, True),), event(12, False))
    assert scope.summary() == (
        "AC-1: biological failure, 1 load back to the last passing test, 1 tray"
    )
