from __future__ import annotations

import pytest

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named
from sterilot.errors import ValidationError
from sterilot.ingest.catalog_import import load_catalog

FILE = """catalog,description,manufacturer,material,complexity,grams
SU-1234,kelly forceps,V Mueller,SS,hinged,60
SU-9001,frazier suction,Pilling,SS,lumened,40
"""


def test_a_clean_file_reads_every_row() -> None:
    result = load_catalog(FILE.replace(",lumened,40", ",simple,40"))
    assert result.clean
    assert [item.catalog for item in result.instruments] == ["SU-1234", "SU-9001"]
    assert result.summary() == "2 new, 0 changed, 0 rejected"


def test_the_instrument_carries_its_details() -> None:
    first = load_catalog(FILE.replace(",lumened,40", ",simple,40")).instruments[0]
    assert first.description == "kelly forceps"
    assert first.complexity is Complexity.HINGED
    assert first.weight is not None
    assert first.weight.grams == pytest.approx(60.0)


def test_a_lumen_measurement_makes_the_item_lumened_without_being_told() -> None:
    text = (
        "catalog,description,manufacturer,lumen_mm,lumen_length\nSU-9001,suction,Pilling,3.0,160\n"
    )
    item = load_catalog(text).instruments[0]
    assert item.complexity is Complexity.LUMENED
    assert item.lumen_diameter_mm == pytest.approx(3.0)


def test_the_defaults_are_stainless_critical_and_simple() -> None:
    text = "catalog,description,manufacturer\nSU-1,probe,Pilling\n"
    item = load_catalog(text).instruments[0]
    assert item.material.code == "SS"
    assert item.criticality is Criticality.CRITICAL
    assert item.complexity is Complexity.SIMPLE


def test_flags_are_read_loosely() -> None:
    text = "catalog,description,manufacturer,complexity,insulated\nSU-2,bipolar,Codman,hinged,yes\n"
    assert load_catalog(text).instruments[0].insulated


def test_foreign_headers_are_aliased() -> None:
    text = "Cat No,Name,Vendor,Mass g\nSU-1,probe,Pilling,45\n"
    item = load_catalog(text).instruments[0]
    assert item.catalog == "SU-1"
    assert item.weight is not None


def test_a_row_that_will_not_build_is_reported() -> None:
    text = "catalog,description,manufacturer,material\nSU-1,probe,Pilling,ZZ\n"
    result = load_catalog(text)
    assert result.instruments == ()
    assert "will not build an instrument" in result.problems[0].describe()


def test_a_repeated_catalog_number_is_reported() -> None:
    text = (
        FILE.replace(",lumened,40", ",simple,40") + "SU-1234,kelly forceps,V Mueller,SS,hinged,60\n"
    )
    result = load_catalog(text)
    assert len(result.instruments) == 2
    assert "repeats a catalog number" in result.problems[0].describe()


def test_an_entry_we_already_hold_is_not_new() -> None:
    known = {
        "SU-1234": Instrument(
            "SU-1234",
            "kelly forceps",
            "V Mueller",
            material_named("SS"),
            complexity=Complexity.HINGED,
        )
    }
    text = "catalog,description,manufacturer,complexity\nSU-1234,kelly forceps,V Mueller,hinged\n"
    result = load_catalog(text, known)
    assert result.instruments == ()
    assert result.changes == ()


def test_a_changed_entry_is_reported_separately() -> None:
    known = {
        "SU-1234": Instrument(
            "SU-1234",
            "kelly forceps",
            "V Mueller",
            material_named("SS"),
            complexity=Complexity.HINGED,
        )
    }
    text = (
        "catalog,description,manufacturer,complexity\nSU-1234,kelly forceps 6in,V Mueller,hinged\n"
    )
    result = load_catalog(text, known)
    assert [item.catalog for item in result.changes] == ["SU-1234"]
    assert result.instruments == ()


def test_a_file_missing_a_required_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        load_catalog("catalog,description\nSU-1,probe\n")
