from __future__ import annotations

import pytest

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.storage.shelf import Location, ParLevel, StorageMap, Zone


def location(**changes: object) -> Location:
    values: dict[str, object] = {
        "code": "st a1",
        "description": "sterile store rack A1",
        "zone": Zone.STERILE_STORE,
        "capacity_units": 24,
        "floor_clearance_cm": 30.0,
        "sprinkler_clearance_cm": 60.0,
    }
    values.update(changes)
    return Location(**values)  # type: ignore[arg-type]


def test_zone_lookup_and_control() -> None:
    assert Zone.named("sterile store") is Zone.STERILE_STORE
    assert Zone.THEATRE_CORE.controlled
    assert not Zone.WARD.controlled
    with pytest.raises(ValidationError):
        Zone.named("basement")


def test_code_is_normalised_and_details_required() -> None:
    assert location().code == "ST-A1"
    with pytest.raises(ValidationError):
        location(description=" ")
    with pytest.raises(ValidationError):
        location(capacity_units=0)


def test_negative_clearances_are_refused() -> None:
    with pytest.raises(ValidationError):
        location(floor_clearance_cm=-1.0)


def test_a_good_shelf_has_no_problems() -> None:
    assert location().usable()
    assert location().problems() == ()


def test_a_low_shelf_is_named_with_its_measurement() -> None:
    problems = location(floor_clearance_cm=10.0).problems()
    assert problems == ("the lowest shelf is 10 cm off the floor, not 25",)


def test_a_shelf_too_close_to_the_sprinkler_is_named() -> None:
    problems = location(sprinkler_clearance_cm=20.0).problems()
    assert problems[0].startswith("the top shelf is 20 cm below the sprinkler")


def test_a_rack_against_an_outside_wall_is_named() -> None:
    assert (
        "the rack is against an outside wall" in location(outside_wall_clearance_cm=2.0).problems()
    )


def test_a_shelf_under_plumbing_is_named_first() -> None:
    assert location(under_plumbing=True).problems()[0] == (
        "the shelf is under a sink or a water line"
    )


def test_an_uncontrolled_zone_is_not_storage() -> None:
    assert "ward is not a controlled area" in location(zone=Zone.WARD).problems()


def test_par_levels_hold_together() -> None:
    par = ParLevel("ort major", 2, 5)
    assert par.code == "ORT-MAJOR"
    assert par.shortfall(1) == 4
    assert par.shortfall(5) == 0
    assert par.shortfall(9) == 0
    assert par.below_minimum(1)
    assert not par.below_minimum(2)


def test_a_par_target_sits_above_its_minimum() -> None:
    with pytest.raises(ValidationError):
        ParLevel("ORT-MAJOR", 5, 2)
    with pytest.raises(ValidationError):
        ParLevel("ORT-MAJOR", -1, 5)


def test_a_negative_count_is_refused() -> None:
    with pytest.raises(ValidationError):
        ParLevel("ORT-MAJOR", 2, 5).shortfall(-1)


def test_a_map_refuses_duplicate_locations_or_pars() -> None:
    with pytest.raises(ConflictError):
        StorageMap(locations=(location(), location()))
    with pytest.raises(ConflictError):
        StorageMap(pars=(ParLevel("ORT-MAJOR", 1, 2), ParLevel("ort major", 1, 3)))


def test_a_map_finds_locations_and_pars() -> None:
    plan = StorageMap(locations=(location(),), pars=(ParLevel("ORT-MAJOR", 2, 5),))
    assert plan.location("st a1").capacity_units == 24
    assert plan.par("ort major") is not None
    assert plan.par("GEN-MINOR") is None
    with pytest.raises(NotFoundError):
        plan.location("ST-Z9")


def test_capacity_counts_only_usable_locations() -> None:
    plan = StorageMap(
        locations=(location(), location(code="ST-A2", capacity_units=12, under_plumbing=True))
    )
    assert plan.capacity() == 24
    assert [item.code for item in plan.unusable()] == ["ST-A2"]


def test_the_build_list_puts_the_worst_shortfall_first() -> None:
    plan = StorageMap(
        pars=(
            ParLevel("ORT-MAJOR", 2, 5),
            ParLevel("GEN-MINOR", 1, 4),
            ParLevel("CYS-1", 1, 2),
        )
    )
    wanted = plan.build_list({"ORT-MAJOR": 4, "GEN-MINOR": 0, "CYS-1": 2})
    assert wanted == (("GEN-MINOR", 4), ("ORT-MAJOR", 1))


def test_a_full_shelf_needs_nothing_built() -> None:
    plan = StorageMap(pars=(ParLevel("ORT-MAJOR", 2, 5),))
    assert plan.build_list({"ORT-MAJOR": 5}) == ()


def test_a_location_prints_its_label() -> None:
    assert str(location()) == "ST-A1 sterile store rack A1"
