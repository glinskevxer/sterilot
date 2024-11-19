from __future__ import annotations

from datetime import date

import pytest

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.revision import RevisionHistory
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import NotFoundError
from sterilot.store.catalog_repo import CatalogStore
from sterilot.store.db import Database
from sterilot.store.migrations import migrate
from sterilot.units.mass import Mass


def store() -> CatalogStore:
    db = Database.in_memory()
    migrate(db)
    return CatalogStore(db)


def forceps() -> Instrument:
    return Instrument(
        "SU-1234",
        "kelly forceps",
        "V Mueller",
        material_named("SS"),
        complexity=Complexity.HINGED,
        weight=Mass.of_grams(60),
    )


def suction() -> Instrument:
    return Instrument(
        "SU-9001",
        "frazier suction",
        "Pilling",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        criticality=Criticality.SEMICRITICAL,
        lumen_diameter_mm=3.0,
        lumen_length_mm=160.0,
        requires_disassembly=True,
    )


def sheet(quantity: int = 6) -> CountSheet:
    return CountSheet.of(
        "ORT-MAJOR",
        "orthopaedic major set",
        [CountLine(forceps(), quantity=quantity, position="stringer 1")],
        container="RC-2001",
    )


def test_an_instrument_round_trips() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    found = catalog.instrument("su 1234")
    assert found == forceps()
    catalog.db.close()


def test_a_lumened_instrument_keeps_its_measurements() -> None:
    catalog = store()
    catalog.save_instrument(suction())
    found = catalog.instrument("SU-9001")
    assert found.lumen_diameter_mm == pytest.approx(3.0)
    assert found.lumen_length_mm == pytest.approx(160.0)
    assert found.requires_disassembly
    assert found.criticality is Criticality.SEMICRITICAL
    catalog.db.close()


def test_an_instrument_with_no_weight_comes_back_without_one() -> None:
    catalog = store()
    plain = Instrument("SU-2", "probe", "Pilling", material_named("SS"))
    catalog.save_instrument(plain)
    assert catalog.instrument("SU-2").weight is None
    catalog.db.close()


def test_saving_the_same_catalog_number_updates_it() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    changed = Instrument(
        "SU-1234",
        "kelly forceps 6in",
        "V Mueller",
        material_named("SS"),
        complexity=Complexity.HINGED,
    )
    catalog.save_instrument(changed)
    assert catalog.instrument("SU-1234").description == "kelly forceps 6in"
    assert len(catalog.instruments()) == 1
    catalog.db.close()


def test_an_unstocked_number_is_refused() -> None:
    catalog = store()
    with pytest.raises(NotFoundError):
        catalog.instrument("SU-0000")
    assert not catalog.stocks("SU-0000")
    catalog.db.close()


def test_instruments_come_back_in_catalog_order() -> None:
    catalog = store()
    catalog.save_instrument(suction())
    catalog.save_instrument(forceps())
    assert [item.catalog for item in catalog.instruments()] == ["SU-1234", "SU-9001"]
    catalog.db.close()


def test_a_sheet_history_round_trips() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    history = RevisionHistory.started(sheet(), date(2024, 1, 1), note="first issue")
    catalog.save_history(history)
    found = catalog.history("ort major")
    assert found.current.number == 1
    assert found.current.note == "first issue"
    assert found.current.sheet.container == "RC-2001"
    assert found.current.sheet.line_for("SU-1234").position == "stringer 1"
    catalog.db.close()


def test_several_revisions_keep_their_windows() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    history = RevisionHistory.started(sheet(6), date(2024, 1, 1))
    history = history.revised(sheet(8), date(2024, 7, 1), note="surgeon request")
    catalog.save_history(history)
    found = catalog.history("ORT-MAJOR")
    assert [item.number for item in found.revisions] == [1, 2]
    assert found.at(date(2024, 3, 1)).sheet.line_for("SU-1234").quantity == 6
    assert found.at(date(2024, 9, 1)).sheet.line_for("SU-1234").quantity == 8
    catalog.db.close()


def test_saving_a_history_again_replaces_it() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_history(RevisionHistory.started(sheet(6), date(2024, 1, 1)))
    catalog.save_history(RevisionHistory.started(sheet(9), date(2024, 1, 1)))
    found = catalog.history("ORT-MAJOR")
    assert len(found.revisions) == 1
    assert found.current.sheet.line_for("SU-1234").quantity == 9
    catalog.db.close()


def test_the_sheet_for_a_day_comes_straight_back() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_history(RevisionHistory.started(sheet(), date(2024, 1, 1)))
    assert catalog.sheet("ORT-MAJOR", date(2024, 5, 1)).code == "ORT-MAJOR"
    catalog.db.close()


def test_an_unknown_set_is_refused() -> None:
    catalog = store()
    with pytest.raises(NotFoundError):
        catalog.history("NOPE")
    catalog.db.close()


def test_set_codes_are_listed() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_history(RevisionHistory.started(sheet(), date(2024, 1, 1)))
    assert catalog.set_codes() == ("ORT-MAJOR",)
    catalog.db.close()
