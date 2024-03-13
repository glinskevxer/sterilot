from __future__ import annotations

import pytest

from sterilot.catalog.instrument import Complexity, Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import ValidationError
from sterilot.methods import Method
from sterilot.units.mass import Mass


def clamp(catalog: str = "SU-1234", grams: float | None = 60.0) -> Instrument:
    return Instrument(
        catalog,
        "kelly forceps",
        "V Mueller",
        material_named("SS"),
        complexity=Complexity.HINGED,
        weight=None if grams is None else Mass.of_grams(grams),
    )


def polymer_retractor() -> Instrument:
    return Instrument(
        "PR-1",
        "polymer retractor",
        "Aesculap",
        material_named("PL"),
        weight=Mass.of_grams(200),
    )


def narrow_suction() -> Instrument:
    return Instrument(
        "SU-9002",
        "micro suction",
        "Pilling",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=0.7,
        lumen_length_mm=140.0,
        weight=Mass.of_grams(40),
    )


def basic_sheet() -> CountSheet:
    return CountSheet.of(
        "ort major",
        "orthopaedic major set",
        [
            CountLine(clamp("SU-1234"), quantity=6, position="stringer 1"),
            CountLine(clamp("SU-1235"), quantity=4, position="stringer 2"),
            CountLine(clamp("SU-1236"), quantity=1, required=False),
        ],
        container="RC-2001",
    )


def test_code_is_normalised_and_name_required() -> None:
    sheet = basic_sheet()
    assert sheet.code == "ORT-MAJOR"
    with pytest.raises(ValidationError):
        CountSheet.of("ORT", "  ", [CountLine(clamp())])


def test_a_sheet_needs_lines() -> None:
    with pytest.raises(ValidationError):
        CountSheet.of("ORT", "set", [])


def test_a_catalog_number_cannot_appear_twice() -> None:
    with pytest.raises(ValidationError):
        CountSheet.of("ORT", "set", [CountLine(clamp()), CountLine(clamp())])


def test_a_line_needs_a_quantity() -> None:
    with pytest.raises(ValidationError):
        CountLine(clamp(), quantity=0)


def test_counts_split_required_from_optional() -> None:
    sheet = basic_sheet()
    assert sheet.item_count == 11
    assert sheet.required_count == 10


def test_line_lookup_normalises_the_catalog_number() -> None:
    sheet = basic_sheet()
    assert sheet.line_for("su 1234").quantity == 6
    assert sheet.holds("SU-1235")
    assert not sheet.holds("SU-9999")


def test_line_lookup_refuses_an_item_not_on_the_sheet() -> None:
    with pytest.raises(ValidationError):
        basic_sheet().line_for("SU-9999")


def test_line_describes_itself() -> None:
    line = CountLine(clamp(), quantity=6, position="stringer 1")
    assert line.describe() == "6 x SU-1234 kelly forceps [stringer 1]"
    assert CountLine(clamp(), required=False).describe().endswith("(optional)")


def test_a_stainless_sheet_takes_every_method() -> None:
    assert set(basic_sheet().methods()) == set(Method)


def test_one_polymer_item_takes_the_whole_sheet_out_of_steam() -> None:
    sheet = CountSheet.of("MIX", "mixed set", [CountLine(clamp()), CountLine(polymer_retractor())])
    assert set(sheet.methods()) == {Method.HYDROGEN_PEROXIDE, Method.ETHYLENE_OXIDE}
    assert not sheet.tolerates(Method.STEAM_PREVAC)


def test_refusals_name_the_item_and_the_reason() -> None:
    sheet = CountSheet.of("MIX", "mixed set", [CountLine(clamp()), CountLine(polymer_retractor())])
    refusals = sheet.refusals_for(Method.STEAM_PREVAC)
    assert list(refusals) == ["PR-1"]
    assert "rated to" in refusals["PR-1"]


def test_a_narrow_lumen_blocks_only_peroxide() -> None:
    sheet = CountSheet.of("SUC", "suction set", [CountLine(clamp()), CountLine(narrow_suction())])
    assert Method.HYDROGEN_PEROXIDE not in sheet.methods()
    assert Method.STEAM_PREVAC in sheet.methods()


def test_known_weight_sums_the_quantities() -> None:
    sheet = basic_sheet()
    assert sheet.known_weight().grams == pytest.approx(660.0)


def test_missing_weights_are_reported_not_guessed() -> None:
    sheet = CountSheet.of(
        "ORT", "set", [CountLine(clamp("SU-1", 60.0)), CountLine(clamp("SU-2", None))]
    )
    assert sheet.weights_missing() == ("SU-2",)
    assert sheet.known_weight().grams == pytest.approx(60.0)


def test_sink_minutes_scale_with_quantity() -> None:
    assert basic_sheet().sink_minutes() == pytest.approx(11.0)


def test_lumened_items_are_listed_for_the_sink() -> None:
    sheet = CountSheet.of("SUC", "suction set", [CountLine(clamp()), CountLine(narrow_suction())])
    assert [item.catalog for item in sheet.lumened_items()] == ["SU-9002"]


def test_container_is_carried() -> None:
    assert basic_sheet().container == "RC-2001"


def test_label() -> None:
    assert str(basic_sheet()) == "ORT-MAJOR orthopaedic major set"
