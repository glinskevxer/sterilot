from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadRegister
from sterilot.methods import Method
from sterilot.recall.notice import RecallAction, Whereabouts, notice_for
from sterilot.recall.scope import (
    QualificationEvent,
    RecallScope,
    Trigger,
    scope_for,
)
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2024, 8, 12)
RAISED = datetime(2024, 8, 12, 14, 0)


def at(hour: int) -> datetime:
    return datetime(2024, 8, 12, hour, 0)


def record(reference: str, run: int, hour: int, assets: tuple[str, ...]) -> LoadRecord:
    cycle = SterilizerCycle(
        LotControlNumber("AC-1", DAY, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        at(hour),
        "T-4471",
        CycleMeasurements(Temperature(133.0), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    load = Load(
        reference,
        Method.STEAM_PREVAC,
        tuple(LoadItem(asset, "ORT-MAJOR") for asset in assets),
        "T-4471",
        at(hour),
    )
    return LoadRecord(load, cycle)


def scope() -> RecallScope:
    register = LoadRegister.of(
        [record("LD-1", 1, 8, ("ORT-0114", "GEN-0207")), record("LD-2", 2, 10, ("ORT-0115",))]
    )
    events = (QualificationEvent("AC-1", Trigger.BIOLOGICAL, at(7), True),)
    return scope_for(
        register, events, QualificationEvent("AC-1", Trigger.BIOLOGICAL, at(13), False)
    )


def test_whereabouts_lookup_and_actions() -> None:
    assert Whereabouts.named("USED") is Whereabouts.USED
    assert Whereabouts.STORAGE.action == "pull from the shelf and quarantine"
    assert not Whereabouts.REPROCESSING.needs_action
    assert Whereabouts.UNKNOWN.needs_action
    with pytest.raises(ValidationError):
        Whereabouts.named("lost")


def test_used_sorts_ahead_of_everything_else() -> None:
    order = sorted(Whereabouts, key=lambda item: item.urgency)
    assert order[0] is Whereabouts.USED
    assert order[-1] is Whereabouts.REPROCESSING


def test_an_action_describes_itself() -> None:
    action = RecallAction("ort 0114", "LD-1", Whereabouts.ISSUED, "OR3 case 07")
    assert action.asset == "ORT-0114"
    assert action.describe() == (
        "ORT-0114 in LD-1, issued (OR3 case 07): retrieve from the room before the case starts"
    )


def test_a_notice_covers_every_tray_in_every_recalled_load() -> None:
    notice = notice_for("rc 2024 03", scope(), {}, RAISED, "T-9002")
    assert notice.reference == "RC-2024-03"
    assert len(notice.actions) == 3


def test_a_tray_with_no_known_location_becomes_an_unknown() -> None:
    notice = notice_for("RC-1", scope(), {"ORT-0114": Whereabouts.STORAGE}, RAISED, "T-9002")
    unknowns = notice.by_whereabouts(Whereabouts.UNKNOWN)
    assert {action.asset for action in unknowns} == {"GEN-0207", "ORT-0115"}


def test_locations_may_carry_detail() -> None:
    notice = notice_for(
        "RC-1",
        scope(),
        {"ORT-0114": (Whereabouts.ISSUED, "OR3 case 07")},
        RAISED,
        "T-9002",
    )
    issued = notice.by_whereabouts(Whereabouts.ISSUED)[0]
    assert issued.detail == "OR3 case 07"


def test_actions_are_ordered_by_urgency_then_tray() -> None:
    notice = notice_for(
        "RC-1",
        scope(),
        {
            "ORT-0114": Whereabouts.STORAGE,
            "GEN-0207": Whereabouts.USED,
            "ORT-0115": Whereabouts.ISSUED,
        },
        RAISED,
        "T-9002",
    )
    assert [action.asset for action in notice.actions] == ["GEN-0207", "ORT-0115", "ORT-0114"]


def test_a_used_tray_makes_it_a_patient_exposure() -> None:
    notice = notice_for("RC-1", scope(), {"GEN-0207": Whereabouts.USED}, RAISED, "T-9002")
    assert notice.patient_exposure
    assert "PATIENT EXPOSURE" in notice.render()


def test_no_used_trays_means_no_exposure_line() -> None:
    notice = notice_for(
        "RC-1",
        scope(),
        {
            "ORT-0114": Whereabouts.STORAGE,
            "GEN-0207": Whereabouts.STORAGE,
            "ORT-0115": Whereabouts.STORAGE,
        },
        RAISED,
        "T-9002",
    )
    assert not notice.patient_exposure
    assert "PATIENT EXPOSURE" not in notice.render()


def test_a_tray_already_back_in_the_loop_needs_no_action() -> None:
    notice = notice_for(
        "RC-1",
        scope(),
        {
            "ORT-0114": Whereabouts.REPROCESSING,
            "GEN-0207": Whereabouts.STORAGE,
            "ORT-0115": Whereabouts.STORAGE,
        },
        RAISED,
        "T-9002",
    )
    assert len(notice.outstanding()) == 2
    assert "ORT-0114" not in [action.asset for action in notice.outstanding()]


def test_the_notice_renders_with_its_heading_and_scope() -> None:
    notice = notice_for("RC-1", scope(), {}, RAISED, "t 9002")
    lines = notice.render().splitlines()
    assert lines[0] == "recall RC-1 raised 2024-08-12 14:00 by T-9002"
    assert lines[1].startswith("AC-1: biological failure")
    assert len(lines) == 5
