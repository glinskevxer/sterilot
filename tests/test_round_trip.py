"""One tray all the way round, with the modules joined up.

The unit tests each hold one rule still and poke it. This one runs a tray from
the sink to the shelf to a case and then recalls it, because most of what goes
wrong in this department happens at a handover rather than inside a step.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sterilot.assets.lifecycle import Stage
from sterilot.assets.tray import TrayInstance
from sterilot.cases.issue import Disposition, Issue, IssueLog
from sterilot.catalog.count import count_tray
from sterilot.catalog.instrument import Complexity, Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.decon.a0 import evaluate as evaluate_a0
from sterilot.ids import LotControlNumber
from sterilot.indicators.chemical import (
    ChemicalIndicator,
    ChemicalResult,
    IndicatorClass,
    Outcome,
    Placement,
)
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadRegister, LoadStatus
from sterilot.load.release import ReleaseKind, ReleaseRequest, decide
from sterilot.methods import Method
from sterilot.recall.notice import Whereabouts, notice_for
from sterilot.recall.scope import QualificationEvent, Trigger, scope_for
from sterilot.settings import Settings
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.storage.event import Event, EventRecord, Package, Packaging
from sterilot.storage.pick import ShelfItem, pick
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.mass import Mass
from sterilot.units.pressure import saturation_pressure
from sterilot.units.temperature import Temperature

DAY = date(2024, 9, 5)
WASH_AT = datetime(2024, 9, 5, 6, 30)
CYCLE_AT = datetime(2024, 9, 5, 8, 0)
RELEASE_AT = datetime(2024, 9, 5, 9, 30)
TECH = "T-4471"


def forceps(catalog: str) -> Instrument:
    return Instrument(
        catalog,
        "kelly forceps",
        "V Mueller",
        material_named("SS"),
        complexity=Complexity.HINGED,
        weight=Mass.of_grams(60),
    )


def sheet() -> CountSheet:
    return CountSheet.of(
        "ORT-MAJOR",
        "orthopaedic major set",
        [CountLine(forceps("SU-1234"), quantity=6), CountLine(forceps("SU-1235"), quantity=4)],
    )


def chamber() -> Sterilizer:
    return Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))


def cycle(run: int = 1, at: datetime = CYCLE_AT) -> SterilizerCycle:
    return SterilizerCycle(
        LotControlNumber("AC-1", at.date(), run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        at,
        TECH,
        CycleMeasurements(
            Temperature(133.0),
            Duration.of_minutes(4),
            Duration.of_minutes(31),
            saturation_pressure(Temperature(133.0)),
            4,
        ),
        Trace.flat(at, 133.0, 240.0, step=20.0),
    )


def strips(asset: str) -> dict[str, tuple[ChemicalResult, ...]]:
    indicator = ChemicalIndicator(
        IndicatorClass.INTEGRATING,
        "CI-24B09",
        date(2025, 1, 31),
        frozenset({Method.STEAM_PREVAC}),
    )
    return {
        asset: (
            ChemicalResult(indicator, Placement.EXTERNAL, Outcome.PASS, RELEASE_AT, TECH),
            ChemicalResult(indicator, Placement.INTERNAL, Outcome.PASS, RELEASE_AT, TECH),
        )
    }


def test_a_tray_goes_round_the_loop_and_ends_up_back_soiled() -> None:
    tray = TrayInstance.placed_in_service("ORT-0114", "ORT-MAJOR", WASH_AT, TECH)
    moves = [
        (Stage.DECONTAMINATION, WASH_AT + timedelta(minutes=10)),
        (Stage.CLEAN, WASH_AT + timedelta(minutes=70)),
        (Stage.ASSEMBLED, WASH_AT + timedelta(minutes=90)),
        (Stage.STERILIZING, CYCLE_AT),
        (Stage.COOLING, CYCLE_AT + timedelta(minutes=35)),
        (Stage.STERILE, RELEASE_AT),
        (Stage.ISSUED, RELEASE_AT + timedelta(hours=2)),
        (Stage.IN_USE, RELEASE_AT + timedelta(hours=3)),
        (Stage.SOILED, RELEASE_AT + timedelta(hours=6)),
    ]
    for stage, at in moves:
        tray = tray.moved_to(stage, at, TECH)
    assert tray.stage is Stage.SOILED
    assert tray.turns_completed() == 1
    assert len(tray.history) == 10


def test_the_wash_the_count_and_the_cycle_all_have_to_pass_for_a_release() -> None:
    wash = evaluate_a0(Trace.flat(WASH_AT, 90.0, 300.0, step=30.0))
    assert wash.passed

    counted = count_tray(sheet(), {"SU-1234": 6, "SU-1235": 4}, day=DAY)
    assert counted.complete

    load = Load.of(
        "LD-9001",
        Method.STEAM_PREVAC,
        [LoadItem("ORT-0114", "ORT-MAJOR", weight=Mass(9.0))],
        TECH,
        CYCLE_AT - timedelta(minutes=20),
    )
    assert load.buildable(chamber().capacity_units)

    decision = decide(
        ReleaseRequest(load, cycle(), chamber(), RELEASE_AT, TECH, strips("ORT-0114"))
    )
    assert decision.kind is ReleaseKind.ROUTINE

    record = LoadRecord(load, cycle()).decided(decision)
    assert record.status is LoadStatus.RELEASED


def test_a_positive_biological_two_days_later_reaches_the_tray_in_the_room() -> None:
    register = LoadRegister()
    for run, asset in ((1, "ORT-0114"), (2, "GEN-0207"), (3, "ORT-0115")):
        at = CYCLE_AT + timedelta(hours=run)
        load = Load.of(
            f"LD-900{run}",
            Method.STEAM_PREVAC,
            [LoadItem(asset, "ORT-MAJOR")],
            TECH,
            at - timedelta(minutes=20),
        )
        record = LoadRecord(load, cycle(run, at))
        decision = decide(
            ReleaseRequest(
                load, cycle(run, at), chamber(), at + timedelta(hours=2), TECH, strips(asset)
            )
        )
        register = register.with_record(record.decided(decision))

    events = (QualificationEvent("AC-1", Trigger.BIOLOGICAL, CYCLE_AT, True),)
    failure = QualificationEvent("AC-1", Trigger.BIOLOGICAL, CYCLE_AT + timedelta(hours=6), False)
    scope = scope_for(register, events, failure)
    assert [record.reference for record in scope.loads] == ["LD-9001", "LD-9002", "LD-9003"]

    log = IssueLog.of(
        [
            Issue("ORT-0114", "OR3-20240905-01", RELEASE_AT, TECH, RELEASE_AT, Disposition.USED),
            Issue("GEN-0207", "OR4-20240905-02", RELEASE_AT, TECH),
        ]
    )
    notice = notice_for("RC-2024-07", scope, log.locations(scope.assets()), failure.at, "T-9002")
    assert notice.patient_exposure
    assert [action.asset for action in notice.actions] == ["ORT-0114", "GEN-0207", "ORT-0115"]
    assert notice.by_whereabouts(Whereabouts.UNKNOWN)[0].asset == "ORT-0115"


def test_a_recalled_tray_is_no_longer_pickable_from_the_shelf() -> None:
    package = Package(
        "ORT-0114", LotControlNumber("AC-1", DAY, 1), Packaging.SEQUENTIAL_WRAP, RELEASE_AT
    )
    shelf = [ShelfItem(package, "ORT-MAJOR", "ST-A1")]
    result = pick(shelf, "ORT-MAJOR", 1, RELEASE_AT + timedelta(hours=1), Settings())
    assert result.complete

    quarantined = package.with_event(
        EventRecord(
            Event.SEAL_BROKEN, RELEASE_AT + timedelta(minutes=30), TECH, "recall RC-2024-07"
        )
    )
    result = pick(
        [ShelfItem(quarantined, "ORT-MAJOR", "ST-A1")],
        "ORT-MAJOR",
        1,
        RELEASE_AT + timedelta(hours=1),
        Settings(),
    )
    assert not result.complete
    assert result.skipped[0].asset == "ORT-0114"
