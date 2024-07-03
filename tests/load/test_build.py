from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.load.build import Load, LoadItem
from sterilot.methods import Method
from sterilot.units.mass import Mass

BUILT_AT = datetime(2024, 6, 20, 7, 40)


def item(asset: str = "ORT-0114", **changes: object) -> LoadItem:
    values: dict[str, object] = {"asset": asset, "code": "ort major", "units": 2}
    values.update(changes)
    return LoadItem(**values)  # type: ignore[arg-type]


def load(**changes: object) -> Load:
    values: dict[str, object] = {
        "reference": "ld 4412",
        "method": Method.STEAM_PREVAC,
        "items": (item("ORT-0114"), item("GEN-0207", code="gen minor")),
        "built_by": "T-4471",
        "built_at": BUILT_AT,
    }
    values.update(changes)
    return Load(**values)  # type: ignore[arg-type]


def test_item_identifiers_are_normalised() -> None:
    made = item("ort 0114")
    assert made.asset == "ORT-0114"
    assert made.code == "ORT-MAJOR"


def test_an_item_takes_space_and_sits_on_a_shelf() -> None:
    with pytest.raises(ValidationError):
        item(units=0)
    with pytest.raises(ValidationError):
        item(shelf=0)


def test_an_item_tolerates_something() -> None:
    with pytest.raises(ValidationError):
        item(methods=frozenset())


def test_a_load_needs_contents_and_unique_trays() -> None:
    with pytest.raises(ValidationError):
        load(items=())
    with pytest.raises(ValidationError):
        load(items=(item("ORT-0114"), item("ort 0114")))


def test_a_load_totals_its_units_and_weight() -> None:
    made = load(
        items=(
            item("ORT-0114", weight=Mass(8.0)),
            item("GEN-0207", code="gen minor", weight=Mass(6.0)),
        )
    )
    assert made.units == 4
    assert made.known_weight().kilograms == pytest.approx(14.0)


def test_an_unweighed_item_does_not_break_the_total() -> None:
    made = load(items=(item("ORT-0114", weight=Mass(8.0)), item("GEN-0207", code="gen minor")))
    assert made.known_weight().kilograms == pytest.approx(8.0)


def test_assets_and_item_lookup() -> None:
    made = load()
    assert made.assets() == ("ORT-0114", "GEN-0207")
    assert made.item("ort 0114").code == "ORT-MAJOR"
    with pytest.raises(ValidationError):
        made.item("NOPE")


def test_a_clean_load_has_no_problems() -> None:
    assert load().buildable()
    assert load().problems() == ()


def test_an_item_that_cannot_take_the_method_is_named() -> None:
    polymer = item("PLY-0001", methods=frozenset({Method.HYDROGEN_PEROXIDE}))
    problems = load(items=(item("ORT-0114"), polymer)).problems()
    assert problems == ("PLY-0001 does not tolerate steam, dynamic air removal",)


def test_a_load_over_the_chamber_capacity_is_named() -> None:
    problems = load().problems(capacity_units=3)
    assert problems == ("the load is 4 units against a chamber of 3",)


def test_a_load_inside_the_chamber_capacity_passes() -> None:
    assert load().buildable(capacity_units=6)


def test_an_overweight_set_is_named_with_the_excess() -> None:
    heavy = item("ORT-0114", weight=Mass(12.0))
    problems = load(items=(heavy,)).problems()
    assert problems[0] == "ORT-0114 is 0.60 kg over the set weight limit"


def test_a_set_exactly_on_the_limit_passes() -> None:
    exact = item("ORT-0114", weight=Mass(11.4))
    assert load(items=(exact,)).buildable()


def test_textiles_have_to_ride_on_the_top_shelf() -> None:
    linen = item("LIN-0001", textile=True, shelf=1)
    tray = item("ORT-0114", shelf=2)
    problems = load(items=(linen, tray)).problems()
    assert problems == ("LIN-0001 is a textile pack below shelf 2",)


def test_a_load_of_textiles_alone_is_fine() -> None:
    linen = item("LIN-0001", textile=True, shelf=1)
    assert load(items=(linen,)).buildable()


def test_textiles_on_the_top_shelf_pass() -> None:
    linen = item("LIN-0001", textile=True, shelf=3)
    tray = item("ORT-0114", shelf=1)
    assert load(items=(linen, tray)).buildable()


def test_an_implant_cannot_go_through_an_immediate_use_cycle() -> None:
    implant = item("IMP-0001", implant=True)
    made = load(method=Method.STEAM_IUSS, items=(implant,))
    assert "an implant cannot go through an immediate use cycle" in made.problems()


def test_an_implant_in_an_ordinary_cycle_is_fine_and_flagged() -> None:
    implant = item("IMP-0001", implant=True)
    made = load(items=(implant,))
    assert made.carries_implant
    assert made.buildable()


def test_a_load_without_implants_or_textiles_says_so() -> None:
    made = load()
    assert not made.carries_implant
    assert not made.carries_textiles


def test_label() -> None:
    assert str(load()) == "LD-4412 (2 items)"
