from __future__ import annotations

import pytest

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named
from sterilot.errors import ValidationError
from sterilot.methods import Method
from sterilot.units.mass import Mass


def clamp() -> Instrument:
    return Instrument(
        "su 1234",
        "kelly forceps 5.5in",
        "V Mueller",
        material_named("SS"),
        complexity=Complexity.HINGED,
    )


def suction() -> Instrument:
    return Instrument(
        "SU-9001",
        "frazier suction tip 10fr",
        "Pilling",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=3.3,
        lumen_length_mm=160.0,
    )


def test_catalog_number_is_normalised() -> None:
    assert clamp().catalog == "SU-1234"


def test_description_and_manufacturer_are_required() -> None:
    with pytest.raises(ValidationError):
        Instrument("SU-1", " ", "V Mueller", material_named("SS"))
    with pytest.raises(ValidationError):
        Instrument("SU-1", "clamp", "", material_named("SS"))


def test_a_lumen_measurement_forces_the_lumened_flag() -> None:
    with pytest.raises(ValidationError):
        Instrument(
            "SU-2",
            "tube",
            "Pilling",
            material_named("SS"),
            complexity=Complexity.SIMPLE,
            lumen_diameter_mm=2.0,
        )


def test_a_lumened_item_needs_its_channel_measured() -> None:
    with pytest.raises(ValidationError):
        Instrument("SU-3", "tube", "Pilling", material_named("SS"), complexity=Complexity.LUMENED)


def test_a_lumen_measurement_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Instrument(
            "SU-4",
            "tube",
            "Pilling",
            material_named("SS"),
            complexity=Complexity.LUMENED,
            lumen_diameter_mm=0.0,
            lumen_length_mm=100.0,
        )


def test_insulated_items_are_never_simple() -> None:
    with pytest.raises(ValidationError):
        Instrument("SU-5", "bipolar forceps", "Codman", material_named("SS"), insulated=True)


def test_complexity_and_criticality_lookup() -> None:
    assert Complexity.named("LUMENED") is Complexity.LUMENED
    assert Criticality.named("semicritical") is Criticality.SEMICRITICAL
    assert Criticality.CRITICAL.must_be_sterile
    assert not Criticality.NONCRITICAL.must_be_sterile
    with pytest.raises(ValidationError):
        Complexity.named("awkward")
    with pytest.raises(ValidationError):
        Criticality.named("very")


def test_sink_time_follows_complexity() -> None:
    assert clamp().sink_minutes == pytest.approx(1.0)
    assert suction().sink_minutes == pytest.approx(4.0)


def test_disassembly_costs_another_minute() -> None:
    item = Instrument(
        "SU-6",
        "trocar assembly",
        "Applied",
        material_named("SS"),
        complexity=Complexity.MULTIPART,
        requires_disassembly=True,
    )
    assert item.sink_minutes == pytest.approx(4.0)


def test_a_stainless_hinge_takes_every_method() -> None:
    assert set(clamp().methods()) == set(Method)


def test_a_wide_short_lumen_takes_peroxide() -> None:
    assert suction().tolerates(Method.HYDROGEN_PEROXIDE)


def test_a_narrow_lumen_is_refused_by_peroxide() -> None:
    item = Instrument(
        "SU-7",
        "micro suction",
        "Pilling",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=0.6,
        lumen_length_mm=120.0,
    )
    assert not item.tolerates(Method.HYDROGEN_PEROXIDE)
    assert "narrower" in str(item.refusal_for(Method.HYDROGEN_PEROXIDE))
    assert item.tolerates(Method.STEAM_PREVAC)


def test_a_long_lumen_is_refused_by_peroxide() -> None:
    item = Instrument(
        "SU-8",
        "long rigid endoscope sheath",
        "Storz",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=4.0,
        lumen_length_mm=620.0,
    )
    assert "longer" in str(item.refusal_for(Method.HYDROGEN_PEROXIDE))


def test_the_material_refusal_wins_before_the_lumen_rule() -> None:
    item = Instrument(
        "SU-9",
        "brass cannula",
        "Pilling",
        material_named("BR"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=0.5,
        lumen_length_mm=100.0,
    )
    assert item.refusal_for(Method.HYDROGEN_PEROXIDE) == (
        "the material is attacked by vaporised peroxide"
    )


def test_a_powered_handpiece_has_no_steam_option() -> None:
    item = Instrument(
        "PW-1",
        "sagittal saw handpiece",
        "Stryker",
        material_named("EL"),
        complexity=Complexity.POWERED,
        weight=Mass.of_grams(900),
    )
    assert not any(item.tolerates(method) for method in Method if method.is_steam)
    assert item.weight is not None


def test_label_reads_like_a_count_sheet_line() -> None:
    assert str(clamp()) == "SU-1234 kelly forceps 5.5in"
