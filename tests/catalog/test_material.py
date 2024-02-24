from __future__ import annotations

import pytest

from sterilot.catalog.material import (
    Material,
    MaterialClass,
    material_named,
    standard_materials,
)
from sterilot.errors import ValidationError
from sterilot.methods import Method
from sterilot.units.temperature import Temperature


def test_material_class_labels_and_lookup() -> None:
    assert MaterialClass.ANODISED_ALUMINIUM.label == "anodised aluminium"
    assert MaterialClass.named("anodised aluminium") is MaterialClass.ANODISED_ALUMINIUM
    assert MaterialClass.named("RIGID-POLYMER") is MaterialClass.RIGID_POLYMER


def test_unknown_material_class_is_refused() -> None:
    with pytest.raises(ValidationError):
        MaterialClass.named("unobtainium")


def test_code_is_normalised_and_name_is_required() -> None:
    material = Material("ss 316", "steel", MaterialClass.STAINLESS)
    assert material.code == "SS-316"
    with pytest.raises(ValidationError):
        Material("SS", "  ", MaterialClass.STAINLESS)


def test_plain_stainless_takes_everything() -> None:
    material = material_named("SS")
    assert set(material.methods()) == set(Method)


def test_cellulose_is_out_of_the_peroxide_chamber() -> None:
    material = material_named("CEL")
    assert not material.tolerates(Method.HYDROGEN_PEROXIDE)
    assert material.refusal_for(Method.HYDROGEN_PEROXIDE) is not None
    assert "absorbs" in str(material.refusal_for(Method.HYDROGEN_PEROXIDE))
    assert material.tolerates(Method.STEAM_PREVAC)


def test_brass_is_attacked_by_peroxide_but_takes_steam() -> None:
    material = material_named("BR")
    assert not material.tolerates(Method.HYDROGEN_PEROXIDE)
    assert material.tolerates(Method.STEAM_GRAVITY)
    assert "attacked" in str(material.refusal_for(Method.HYDROGEN_PEROXIDE))


def test_a_low_temperature_polymer_is_out_of_every_steam_cycle() -> None:
    material = material_named("PL")
    assert not any(material.tolerates(method) for method in Method if method.is_steam)
    assert material.tolerates(Method.HYDROGEN_PEROXIDE)
    assert material.tolerates(Method.ETHYLENE_OXIDE)


def test_a_high_temperature_polymer_takes_gravity_but_not_prevac() -> None:
    material = material_named("PC")
    assert material.tolerates(Method.STEAM_GRAVITY)
    assert material.tolerates(Method.STEAM_PREVAC)


def test_a_polymer_rated_below_the_cycle_names_its_ceiling() -> None:
    material = Material(
        "PX", "polymer", MaterialClass.RIGID_POLYMER, max_temperature=Temperature(125.0)
    )
    reason = material.refusal_for(Method.STEAM_PREVAC)
    assert reason is not None
    assert "125.0 C" in reason


def test_electronics_never_see_steam() -> None:
    material = material_named("EL")
    assert not any(material.tolerates(method) for method in Method if method.is_steam)
    assert (
        material.refusal_for(Method.STEAM_PREVAC) == "powered devices do not go in a steam chamber"
    )
    assert not material.immersible


def test_anodised_aluminium_survives_a_hundred_and_thirty_two() -> None:
    material = material_named("AL-AN")
    assert material.tolerates(Method.STEAM_PREVAC)
    assert material.tolerates(Method.HYDROGEN_PEROXIDE)


def test_the_standard_list_is_keyed_by_code() -> None:
    materials = standard_materials()
    assert materials["SS"].name == "surgical stainless steel"
    assert len(materials) == len(set(materials))
    assert all(code == material.code for code, material in materials.items())


def test_material_named_normalises_what_it_is_given() -> None:
    assert material_named("al an").code == "AL-AN"
    assert material_named(" ss ").code == "SS"


def test_an_unknown_material_is_refused() -> None:
    with pytest.raises(ValidationError):
        material_named("XX")


def test_methods_come_back_in_declaration_order() -> None:
    material = material_named("PL")
    assert material.methods() == (Method.HYDROGEN_PEROXIDE, Method.ETHYLENE_OXIDE)
