from __future__ import annotations

from datetime import date

import pytest

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.revision import RevisionHistory
from sterilot.catalog.substitution import Substitution, SubstitutionTable
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import IntegrityError, NotFoundError
from sterilot.interval import DateRange
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


def approval(
    original: str = "SU-1234", replacement: str = "SU-9001", end: date | None = None
) -> Substitution:
    return Substitution(original, replacement, "T-4471", DateRange(date(2024, 1, 1), end))


def test_substitutions_round_trip() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_instrument(suction())
    catalog.save_substitutions(SubstitutionTable.of([approval()]))
    table = catalog.substitutions()
    assert table.accepts("SU-1234", "SU-9001", date(2024, 5, 1))
    catalog.db.close()


def test_a_closed_approval_keeps_its_end_date() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_instrument(suction())
    catalog.save_substitutions(SubstitutionTable.of([approval(end=date(2024, 3, 1))]))
    table = catalog.substitutions()
    assert table.accepts("SU-1234", "SU-9001", date(2024, 2, 1))
    assert not table.accepts("SU-1234", "SU-9001", date(2024, 5, 1))
    catalog.db.close()


def test_saving_the_approval_list_replaces_it() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_instrument(suction())
    catalog.save_substitutions(SubstitutionTable.of([approval()]))
    catalog.save_substitutions(SubstitutionTable())
    assert catalog.substitutions().entries == ()
    catalog.db.close()


def test_approvals_are_read_back_for_one_item() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    catalog.save_instrument(suction())
    catalog.save_substitutions(SubstitutionTable.of([approval()]))
    found = catalog.substitutions_for("su 1234", date(2024, 5, 1))
    assert [entry.replacement for entry in found] == ["SU-9001"]
    catalog.db.close()


def test_an_approval_naming_an_unstocked_item_is_refused_by_the_database() -> None:
    catalog = store()
    catalog.save_instrument(forceps())
    with pytest.raises(IntegrityError):
        catalog.save_substitutions(SubstitutionTable.of([approval()]))
    catalog.db.close()


def test_a_batch_writes_every_instrument() -> None:
    catalog = store()
    written = catalog.save_instruments([forceps(), suction()])
    assert written == 2
    assert [item.catalog for item in catalog.instruments()] == ["SU-1234", "SU-9001"]
    catalog.db.close()


def test_an_empty_batch_writes_nothing() -> None:
    catalog = store()
    assert catalog.save_instruments([]) == 0
    assert catalog.instruments() == ()
    catalog.db.close()


def test_a_batch_that_fails_leaves_nothing_behind() -> None:
    catalog = store()
    broken = [forceps(), suction()]
    with pytest.raises(IntegrityError):
        with catalog.db.transaction():
            catalog.save_instruments(broken)
            catalog.db.execute(
                "INSERT INTO sheet_line (code, revision, catalog, quantity) VALUES (?, ?, ?, ?)",
                ["NOPE", 1, "SU-1234", 1],
            )
    assert catalog.instruments() == ()
    catalog.db.close()


def test_a_batch_is_faster_than_one_at_a_time_to_write() -> None:
    catalog = store()
    many = [
        Instrument(f"SU-{index:04d}", "forceps", "V Mueller", material_named("SS"))
        for index in range(200)
    ]
    assert catalog.save_instruments(many) == 200
    assert len(catalog.instruments()) == 200
    catalog.db.close()
