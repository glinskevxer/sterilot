from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.assets.lifecycle import Stage
from sterilot.assets.tray import Ownership, TrayInstance, by_stage
from sterilot.errors import ConflictError, ValidationError

START = datetime(2024, 4, 1, 8, 0)


def tray(asset: str = "ort 0114") -> TrayInstance:
    return TrayInstance.placed_in_service(asset, "ort major", START, "T-4471")


def test_ownership_lookup_and_rules() -> None:
    assert Ownership.named("LOANER") is Ownership.LOANER
    assert Ownership.DEPARTMENT.is_ours
    assert Ownership.LOANER.must_be_returned
    assert not Ownership.CONSIGNMENT.must_be_returned
    with pytest.raises(ValidationError):
        Ownership.named("rented")


def test_a_new_tray_starts_soiled_with_one_event() -> None:
    item = tray()
    assert item.asset == "ORT-0114"
    assert item.code == "ORT-MAJOR"
    assert item.stage is Stage.SOILED
    assert len(item.history) == 1
    assert item.history[0].note == "placed in service"


def test_an_outside_tray_has_to_name_its_owner() -> None:
    with pytest.raises(ValidationError):
        TrayInstance.placed_in_service(
            "LN-1", "ORT-MAJOR", START, "T-4471", ownership=Ownership.LOANER
        )


def test_our_own_tray_has_no_outside_owner() -> None:
    with pytest.raises(ValidationError):
        TrayInstance.placed_in_service("A-1", "ORT-MAJOR", START, "T-4471", owner="Acme")


def test_a_tray_needs_a_first_event() -> None:
    with pytest.raises(ValidationError):
        TrayInstance("A-1", "ORT-MAJOR")


def test_moves_follow_the_transition_table() -> None:
    item = tray().moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 8, 30), "T-4471")
    assert item.stage is Stage.DECONTAMINATION
    with pytest.raises(ConflictError):
        item.moved_to(Stage.STERILE, datetime(2024, 4, 1, 9, 0), "T-4471")


def test_a_move_cannot_predate_the_last_one() -> None:
    item = tray().moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 8, 30), "T-4471")
    with pytest.raises(ValidationError):
        item.moved_to(Stage.CLEAN, datetime(2024, 4, 1, 8, 0), "T-4471")


def test_history_is_appended_not_replaced() -> None:
    first = tray()
    second = first.moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 8, 30), "T-4471")
    assert len(first.history) == 1
    assert len(second.history) == 2


def test_the_full_loop_lands_back_on_soiled() -> None:
    item = tray()
    when = START
    for stage in (
        Stage.DECONTAMINATION,
        Stage.CLEAN,
        Stage.ASSEMBLED,
        Stage.STERILIZING,
        Stage.COOLING,
        Stage.STERILE,
        Stage.ISSUED,
        Stage.IN_USE,
        Stage.SOILED,
    ):
        when = when.replace(hour=when.hour + 1)
        item = item.moved_to(stage, when, "T-4471")
    assert item.stage is Stage.SOILED
    assert item.turns_completed() == 1


def test_stage_at_reads_the_history() -> None:
    item = tray().moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 9, 0), "T-4471")
    assert item.stage_at(datetime(2024, 3, 1)) is None
    assert item.stage_at(datetime(2024, 4, 1, 8, 30)) is Stage.SOILED
    assert item.stage_at(datetime(2024, 4, 1, 9, 30)) is Stage.DECONTAMINATION


def test_time_in_stage() -> None:
    item = tray()
    assert item.time_in_stage(datetime(2024, 4, 1, 9, 0)).minutes == pytest.approx(60.0)
    with pytest.raises(ValidationError):
        item.time_in_stage(datetime(2024, 3, 1))


def test_events_in_a_stage() -> None:
    item = tray().moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 9, 0), "T-4471")
    item = item.moved_to(Stage.SOILED, datetime(2024, 4, 1, 9, 30), "T-4471", "rewash")
    assert len(item.events_in(Stage.SOILED)) == 2
    assert item.events_in(Stage.SOILED)[1].note == "rewash"


def test_retiring_a_tray_stops_it_moving() -> None:
    item = tray().retired_on_day(date(2024, 9, 1), "T-4471")
    assert item.retired
    with pytest.raises(ConflictError):
        item.moved_to(Stage.DECONTAMINATION, datetime(2024, 9, 2, 8, 0), "T-4471")


def test_retiring_twice_is_refused() -> None:
    item = tray().retired_on_day(date(2024, 9, 1), "T-4471")
    with pytest.raises(ConflictError):
        item.retired_on_day(date(2024, 9, 2), "T-4471")


def test_history_must_be_in_order() -> None:
    item = tray().moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 9, 0), "T-4471")
    with pytest.raises(ValidationError):
        TrayInstance("A-1", "ORT-MAJOR", history=(item.history[1], item.history[0]))


def test_label() -> None:
    assert str(tray()) == "ORT-0114 (ORT-MAJOR)"


def test_grouping_for_the_floor_board() -> None:
    first = tray("ORT-0114")
    second = tray("ORT-0115").moved_to(Stage.DECONTAMINATION, datetime(2024, 4, 1, 9, 0), "T-4471")
    third = tray("ORT-0113")
    grouped = by_stage([first, second, third])
    assert [item.asset for item in grouped[Stage.SOILED]] == ["ORT-0113", "ORT-0114"]
    assert [item.asset for item in grouped[Stage.DECONTAMINATION]] == ["ORT-0115"]
