from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.assets.lifecycle import Stage
from sterilot.assets.tray import Ownership, TrayInstance
from sterilot.errors import NotFoundError
from sterilot.store.db import Database
from sterilot.store.migrations import migrate
from sterilot.store.tray_repo import TrayStore

START = datetime(2024, 11, 5, 8, 0)


def store() -> TrayStore:
    db = Database.in_memory()
    migrate(db)
    return TrayStore(db)


def tray(asset: str = "ORT-0114", code: str = "ORT-MAJOR") -> TrayInstance:
    return TrayInstance.placed_in_service(asset, code, START, "T-4471")


def moved(item: TrayInstance, *stages: Stage) -> TrayInstance:
    at = START
    for index, stage in enumerate(stages, start=1):
        at = START.replace(hour=START.hour + index)
        item = item.moved_to(stage, at, "T-4471")
    return item


def test_a_tray_round_trips_with_its_history() -> None:
    trays = store()
    item = moved(tray(), Stage.DECONTAMINATION, Stage.CLEAN)
    trays.save(item)
    found = trays.get("ort 0114")
    assert found.asset == "ORT-0114"
    assert found.stage is Stage.CLEAN
    assert len(found.history) == 3
    trays.db.close()


def test_an_unknown_tray_is_refused() -> None:
    trays = store()
    with pytest.raises(NotFoundError):
        trays.get("XX-1")
    assert not trays.exists("XX-1")
    trays.db.close()


def test_saving_again_appends_only_the_new_events() -> None:
    trays = store()
    item = tray()
    trays.save(item)
    trays.save(moved(item, Stage.DECONTAMINATION))
    found = trays.get("ORT-0114")
    assert len(found.history) == 2
    assert found.stage is Stage.DECONTAMINATION
    trays.db.close()


def test_an_outside_tray_keeps_its_owner() -> None:
    trays = store()
    loaner = TrayInstance.placed_in_service(
        "LN-1", "REV-KNEE", START, "T-4471", ownership=Ownership.LOANER, owner="Medline Ortho"
    )
    trays.save(loaner)
    found = trays.get("LN-1")
    assert found.ownership is Ownership.LOANER
    assert found.owner == "Medline Ortho"
    trays.db.close()


def test_trays_of_a_set_come_back_in_order() -> None:
    trays = store()
    trays.save(tray("ORT-0115"))
    trays.save(tray("ORT-0114"))
    trays.save(tray("GEN-0207", "GEN-MINOR"))
    assert [item.asset for item in trays.of_code("ort major")] == ["ORT-0114", "ORT-0115"]
    trays.db.close()


def test_trays_are_found_by_where_they_are_now() -> None:
    trays = store()
    trays.save(moved(tray("ORT-0114"), Stage.DECONTAMINATION, Stage.CLEAN))
    trays.save(moved(tray("ORT-0115"), Stage.DECONTAMINATION))
    assert [item.asset for item in trays.in_stage(Stage.CLEAN)] == ["ORT-0114"]
    assert [item.asset for item in trays.in_stage(Stage.DECONTAMINATION)] == ["ORT-0115"]
    assert trays.in_stage(Stage.STERILE) == ()
    trays.db.close()


def test_the_floor_board_counts_by_stage() -> None:
    trays = store()
    trays.save(moved(tray("ORT-0114"), Stage.DECONTAMINATION))
    trays.save(moved(tray("ORT-0115"), Stage.DECONTAMINATION))
    trays.save(tray("ORT-0116"))
    counts = trays.counts_by_stage()
    assert counts[Stage.DECONTAMINATION] == 2
    assert counts[Stage.SOILED] == 1
    trays.db.close()


def test_retired_trays_are_listed() -> None:
    trays = store()
    trays.save(tray("ORT-0114").retired_on_day(date(2024, 6, 1), "T-4471"))
    trays.save(tray("ORT-0115"))
    assert [item.asset for item in trays.retired()] == ["ORT-0114"]
    assert trays.retired(date(2024, 1, 1)) == ()
    assert [item.asset for item in trays.retired(date(2024, 12, 1))] == ["ORT-0114"]
    trays.db.close()


def test_a_retired_tray_keeps_its_date() -> None:
    trays = store()
    trays.save(tray().retired_on_day(date(2024, 6, 1), "T-4471"))
    assert trays.get("ORT-0114").retired_on == date(2024, 6, 1)
    trays.db.close()


def test_two_moves_in_the_same_second_still_read_in_order() -> None:
    trays = store()
    item = tray()
    item = item.moved_to(Stage.DECONTAMINATION, START, "T-4471")
    item = item.moved_to(Stage.CLEAN, START, "T-4471")
    trays.save(item)
    assert trays.get("ORT-0114").stage is Stage.CLEAN
    assert [found.asset for found in trays.in_stage(Stage.CLEAN)] == ["ORT-0114"]
    assert trays.counts_by_stage() == {Stage.CLEAN: 1}
    trays.db.close()


def test_a_tray_reaching_the_same_stage_twice_in_a_second_keeps_both_events() -> None:
    trays = store()
    item = tray()
    for stage in (
        Stage.DECONTAMINATION,
        Stage.CLEAN,
        Stage.ASSEMBLED,
        Stage.STERILIZING,
        Stage.COOLING,
        Stage.STERILE,
        Stage.ISSUED,
        Stage.STERILE,
    ):
        item = item.moved_to(stage, START, "T-4471")
    trays.save(item)
    found = trays.get("ORT-0114")
    assert found.stage is Stage.STERILE
    assert len(found.history) == 9
    assert len(found.events_in(Stage.STERILE)) == 2
    trays.db.close()
