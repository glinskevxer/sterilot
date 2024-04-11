from __future__ import annotations

from datetime import datetime
from itertools import pairwise

import pytest

from sterilot.assets.lifecycle import (
    Stage,
    TrayEvent,
    allowed_from,
    check_move,
    may_move,
    route,
)
from sterilot.errors import ConflictError, ValidationError


def test_stage_labels_and_lookup() -> None:
    assert Stage.OUT_OF_SERVICE.label == "out of service"
    assert Stage.named("out of service") is Stage.OUT_OF_SERVICE
    assert Stage.named("IN-USE") is Stage.IN_USE


def test_an_unknown_stage_is_refused() -> None:
    with pytest.raises(ValidationError):
        Stage.named("somewhere")


def test_only_two_stages_claim_sterile_contents() -> None:
    assert {stage for stage in Stage if stage.is_sterile} == {Stage.STERILE, Stage.ISSUED}


def test_only_sterile_storage_is_available_to_pick() -> None:
    assert Stage.STERILE.is_available
    assert not Stage.ISSUED.is_available
    assert not Stage.ASSEMBLED.is_available


def test_the_stages_that_send_a_tray_round_again() -> None:
    assert {stage for stage in Stage if stage.needs_reprocessing} == {
        Stage.SOILED,
        Stage.IN_USE,
        Stage.QUARANTINED,
    }


def test_the_ordinary_loop_runs_end_to_end() -> None:
    loop = [
        Stage.SOILED,
        Stage.DECONTAMINATION,
        Stage.CLEAN,
        Stage.ASSEMBLED,
        Stage.STERILIZING,
        Stage.COOLING,
        Stage.STERILE,
        Stage.ISSUED,
        Stage.IN_USE,
        Stage.SOILED,
    ]
    for current, target in pairwise(loop):
        assert may_move(current, target), f"{current} to {target}"


def test_a_tray_cannot_appear_in_storage_without_a_chamber() -> None:
    assert not may_move(Stage.ASSEMBLED, Stage.STERILE)
    assert not may_move(Stage.CLEAN, Stage.STERILE)
    assert not may_move(Stage.SOILED, Stage.CLEAN)


def test_quarantine_and_out_of_service_are_reachable_from_anywhere() -> None:
    for stage in Stage:
        if stage is not Stage.QUARANTINED:
            assert may_move(stage, Stage.QUARANTINED), stage
        if stage is not Stage.OUT_OF_SERVICE:
            assert may_move(stage, Stage.OUT_OF_SERVICE), stage


def test_coming_back_from_quarantine_costs_a_full_loop() -> None:
    assert allowed_from(Stage.QUARANTINED) == frozenset({Stage.SOILED, Stage.OUT_OF_SERVICE})


def test_an_unopened_tray_can_go_back_on_the_shelf() -> None:
    assert may_move(Stage.ISSUED, Stage.STERILE)


def test_moving_nowhere_is_refused() -> None:
    with pytest.raises(ConflictError):
        check_move(Stage.CLEAN, Stage.CLEAN)


def test_an_illegal_move_names_both_ends() -> None:
    with pytest.raises(ConflictError) as caught:
        check_move(Stage.SOILED, Stage.STERILE)
    assert caught.value.context == {"current": "soiled", "target": "sterile"}


def test_a_legal_move_passes_quietly() -> None:
    check_move(Stage.SOILED, Stage.DECONTAMINATION)


def test_an_event_normalises_its_badge_and_describes_itself() -> None:
    event = TrayEvent(datetime(2024, 5, 1, 9, 30), Stage.CLEAN, "t 4471", note="rewashed")
    assert event.by == "T-4471"
    assert str(event) == "2024-05-01 09:30 clean by T-4471, rewashed"


def test_an_event_without_a_note_leaves_it_off() -> None:
    event = TrayEvent(datetime(2024, 5, 1, 9, 30), Stage.CLEAN, "T-4471")
    assert str(event) == "2024-05-01 09:30 clean by T-4471"


def test_route_from_a_stage_to_itself_is_one_step() -> None:
    assert route(Stage.CLEAN, Stage.CLEAN) == (Stage.CLEAN,)


def test_route_walks_the_loop() -> None:
    path = route(Stage.SOILED, Stage.STERILE)
    assert path[0] is Stage.SOILED
    assert path[-1] is Stage.STERILE
    assert Stage.STERILIZING in path
    assert len(path) == 7


def test_route_out_of_quarantine_goes_the_long_way() -> None:
    path = route(Stage.QUARANTINED, Stage.STERILE)
    assert path[1] is Stage.SOILED
    assert len(path) == 8
