from __future__ import annotations

from datetime import date

import pytest

from sterilot.catalog.instrument import Instrument
from sterilot.catalog.material import Material, MaterialClass, material_named
from sterilot.catalog.registry import Catalog
from sterilot.catalog.revision import RevisionHistory
from sterilot.catalog.substitution import Substitution, SubstitutionTable
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import ConflictError, NotFoundError
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.units.temperature import Temperature

DAY = date(2024, 5, 1)


def item(catalog: str, material: str = "SS") -> Instrument:
    return Instrument(catalog, "forceps", "V Mueller", material_named(material))


def sheet(code: str, catalogs: list[str], material: str = "SS") -> CountSheet:
    return CountSheet.of(
        code, f"{code} set", [CountLine(item(catalog, material)) for catalog in catalogs]
    )


def catalog() -> Catalog:
    return Catalog.build(
        instruments=[item("SU-1"), item("SU-2"), item("SU-9")],
        histories=[
            RevisionHistory.started(sheet("ORT-MAJOR", ["SU-1", "SU-2"]), date(2024, 1, 1)),
            RevisionHistory.started(sheet("GEN-MINOR", ["SU-2"]), date(2024, 1, 1)),
        ],
        substitutions=SubstitutionTable.of(
            [Substitution("SU-1", "SU-9", "T-4471", DateRange.starting(date(2024, 1, 1)))]
        ),
    )


def test_an_empty_catalog_is_a_working_object() -> None:
    empty = Catalog.build()
    assert empty.set_codes() == ()
    assert empty.problems(DAY) == ()


def test_a_catalog_number_cannot_be_stocked_twice() -> None:
    with pytest.raises(ConflictError):
        Catalog.build(instruments=[item("SU-1"), item("su 1")])


def test_a_set_code_cannot_be_defined_twice() -> None:
    history = RevisionHistory.started(sheet("ORT-MAJOR", ["SU-1"]), date(2024, 1, 1))
    with pytest.raises(ConflictError):
        Catalog.build(histories=[history, history])


def test_instrument_lookup_normalises() -> None:
    assert catalog().instrument("su 1").catalog == "SU-1"
    assert catalog().stocks("SU-2")
    assert not catalog().stocks("SU-77")


def test_an_unstocked_catalog_number_is_refused() -> None:
    with pytest.raises(NotFoundError):
        catalog().instrument("SU-77")


def test_set_lookup_and_codes() -> None:
    assert catalog().set_codes() == ("GEN-MINOR", "ORT-MAJOR")
    assert catalog().current_sheet("ort major").code == "ORT-MAJOR"
    with pytest.raises(NotFoundError):
        catalog().history("NOPE")


def test_the_sheet_comes_from_the_day_asked_for() -> None:
    base = catalog()
    history = base.history("ORT-MAJOR").revised(
        sheet("ORT-MAJOR", ["SU-1", "SU-2", "SU-9"]), date(2024, 7, 1)
    )
    grown = base.with_history(history)
    assert len(grown.sheet("ORT-MAJOR", date(2024, 5, 1)).lines) == 2
    assert len(grown.sheet("ORT-MAJOR", date(2024, 8, 1)).lines) == 3


def test_sets_containing_finds_every_set_calling_for_an_item() -> None:
    assert catalog().sets_containing("SU-2", DAY) == ("GEN-MINOR", "ORT-MAJOR")
    assert catalog().sets_containing("SU-1", DAY) == ("ORT-MAJOR",)
    assert catalog().sets_containing("SU-9", DAY) == ()


def test_sets_containing_ignores_a_set_not_yet_in_force() -> None:
    base = catalog().with_history(
        RevisionHistory.started(sheet("NEW-SET", ["SU-1"]), date(2025, 1, 1))
    )
    assert "NEW-SET" not in base.sets_containing("SU-1", DAY)


def test_sets_for_method_filters_by_what_the_contents_tolerate() -> None:
    base = (
        catalog()
        .with_instrument(item("PL-1", "PL"))
        .with_history(RevisionHistory.started(sheet("POLY-SET", ["PL-1"], "PL"), date(2024, 1, 1)))
    )
    assert "POLY-SET" not in base.sets_for_method(Method.STEAM_PREVAC, DAY)
    assert "POLY-SET" in base.sets_for_method(Method.HYDROGEN_PEROXIDE, DAY)


def test_a_clean_catalog_reports_no_problems() -> None:
    assert catalog().problems(DAY) == ()


def test_a_sheet_calling_for_an_unstocked_item_is_a_problem() -> None:
    base = Catalog.build(
        instruments=[item("SU-1")],
        histories=[RevisionHistory.started(sheet("ORT-MAJOR", ["SU-1", "SU-7"]), date(2024, 1, 1))],
    )
    assert base.problems(DAY) == ("ORT-MAJOR calls for SU-7, which we do not stock",)


def test_a_substitution_naming_an_unstocked_item_is_a_problem() -> None:
    base = Catalog.build(
        instruments=[item("SU-1")],
        substitutions=SubstitutionTable.of(
            [Substitution("SU-1", "SU-9", "T-4471", DateRange.starting(date(2024, 1, 1)))]
        ),
    )
    assert base.problems(DAY) == ("substitution offers SU-9, which we do not stock",)


def test_a_set_with_no_workable_method_is_a_problem() -> None:
    delicate = Material(
        "PX", "polymer rated to forty", MaterialClass.RIGID_POLYMER, Temperature(40.0)
    )
    soft = Instrument("PX-1", "sizer", "Aesculap", delicate)
    paper = item("CEL-1", "CEL")
    mixed = CountSheet.of("MIX", "impossible set", [CountLine(soft), CountLine(paper)])
    base = Catalog.build(
        instruments=[soft, paper],
        histories=[RevisionHistory.started(mixed, date(2024, 1, 1))],
    )
    assert base.problems(DAY) == ("MIX has no sterilization method its contents all tolerate",)


def test_adding_an_instrument_leaves_the_original_alone() -> None:
    base = catalog()
    grown = base.with_instrument(item("SU-5"))
    assert not base.stocks("SU-5")
    assert grown.stocks("SU-5")


def test_adding_a_stocked_number_again_is_refused() -> None:
    with pytest.raises(ConflictError):
        catalog().with_instrument(item("SU-1"))


def test_substitutions_can_be_replaced_wholesale() -> None:
    base = catalog().with_substitutions(SubstitutionTable())
    assert base.substitutions.active(DAY) == ()
