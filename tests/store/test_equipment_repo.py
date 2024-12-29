from __future__ import annotations

from datetime import date

import pytest

from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import NotFoundError, ValidationError
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.sterilizer.equipment import ChamberSize, Sterilizer
from sterilot.store.db import Database
from sterilot.store.equipment_repo import EquipmentStore
from sterilot.store.migrations import migrate


def store() -> EquipmentStore:
    db = Database.in_memory()
    migrate(db)
    return EquipmentStore(db)


def chamber(**changes: object) -> Sterilizer:
    values: dict[str, object] = {
        "equipment": "AC-1",
        "model": "Amsco 400",
        "manufacturer": "Steris",
        "methods": frozenset({Method.STEAM_PREVAC, Method.STEAM_IUSS}),
        "chamber": ChamberSize.DOUBLE,
        "installed_on": date(2019, 6, 1),
    }
    values.update(changes)
    return Sterilizer(**values)  # type: ignore[arg-type]


def machine(**changes: object) -> Washer:
    values: dict[str, object] = {
        "equipment": "WD-2",
        "model": "Reliance 444",
        "manufacturer": "Steris",
        "washer_class": WasherClass.SINGLE_CHAMBER,
        "last_qualification": date(2024, 1, 10),
    }
    values.update(changes)
    return Washer(**values)  # type: ignore[arg-type]


def test_a_sterilizer_round_trips() -> None:
    units = store()
    units.save_sterilizer(chamber())
    found = units.sterilizer("ac 1")
    assert found.methods == frozenset({Method.STEAM_PREVAC, Method.STEAM_IUSS})
    assert found.chamber is ChamberSize.DOUBLE
    assert found.installed_on == date(2019, 6, 1)
    assert found.usable_on(date(2024, 12, 1))
    units.db.close()


def test_a_repaired_sterilizer_keeps_its_qualification_debt() -> None:
    units = store()
    units.save_sterilizer(chamber().repaired())
    found = units.sterilizer("AC-1")
    assert found.qualification_runs_owed == 3
    assert not found.usable_on(date(2024, 12, 1))
    units.db.close()


def test_a_retired_sterilizer_keeps_its_window() -> None:
    units = store()
    units.save_sterilizer(chamber(in_service=DateRange(date(2019, 6, 1), date(2024, 1, 1))))
    found = units.sterilizer("AC-1")
    assert not found.in_service_on(date(2024, 12, 1))
    units.db.close()


def test_a_washer_round_trips() -> None:
    units = store()
    units.save_washer(machine())
    found = units.washer("wd 2")
    assert found.washer_class is WasherClass.SINGLE_CHAMBER
    assert found.last_qualification == date(2024, 1, 10)
    assert found.disinfects
    units.db.close()


def test_a_tunnel_washer_keeps_its_chamber_count() -> None:
    units = store()
    units.save_washer(machine(washer_class=WasherClass.TUNNEL, chambers=4))
    assert units.washer("WD-2").chambers == 4
    units.db.close()


def test_asking_for_the_wrong_kind_is_refused() -> None:
    units = store()
    units.save_washer(machine())
    with pytest.raises(ValidationError):
        units.sterilizer("WD-2")
    units.save_sterilizer(chamber())
    with pytest.raises(ValidationError):
        units.washer("AC-1")
    units.db.close()


def test_an_unknown_machine_is_refused() -> None:
    units = store()
    with pytest.raises(NotFoundError):
        units.sterilizer("AC-9")
    assert not units.exists("AC-9")
    units.db.close()


def test_machines_are_listed_by_kind() -> None:
    units = store()
    units.save_sterilizer(chamber())
    units.save_sterilizer(chamber(equipment="AC-2"))
    units.save_washer(machine())
    assert [item.equipment for item in units.sterilizers()] == ["AC-1", "AC-2"]
    assert [item.equipment for item in units.washers()] == ["WD-2"]
    assert units.kind_of("AC-1") == "sterilizer"
    units.db.close()


def test_out_of_order_machines_are_listed() -> None:
    units = store()
    units.save_sterilizer(chamber(out_of_order=True))
    units.save_washer(machine())
    assert units.out_of_order() == ("AC-1",)
    units.db.close()
