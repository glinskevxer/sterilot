from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.methods import Method, MethodProfile
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


@pytest.mark.parametrize(
    ("text", "method"),
    [
        ("steam_prevac", Method.STEAM_PREVAC),
        ("prevac", Method.STEAM_PREVAC),
        ("pre-vacuum", Method.STEAM_PREVAC),
        ("dynamic air removal", Method.STEAM_PREVAC),
        ("gravity", Method.STEAM_GRAVITY),
        ("IUSS", Method.STEAM_IUSS),
        ("flash", Method.STEAM_IUSS),
        ("vh2o2", Method.HYDROGEN_PEROXIDE),
        ("peroxide", Method.HYDROGEN_PEROXIDE),
        ("EtO", Method.ETHYLENE_OXIDE),
        ("eo", Method.ETHYLENE_OXIDE),
    ],
)
def test_methods_are_named_the_way_the_floor_names_them(text: str, method: Method) -> None:
    assert Method.named(text) is method


def test_an_unknown_method_is_refused() -> None:
    with pytest.raises(ValidationError):
        Method.named("microwave")


def test_labels_read_like_the_policy_manual() -> None:
    assert Method.STEAM_PREVAC.label == "steam, dynamic air removal"
    assert str(Method.ETHYLENE_OXIDE) == "ethylene oxide"


def test_steam_and_low_temperature_split_the_methods() -> None:
    steam = [m for m in Method if m.is_steam]
    low = [m for m in Method if m.is_low_temperature]
    assert set(steam) == {Method.STEAM_PREVAC, Method.STEAM_GRAVITY, Method.STEAM_IUSS}
    assert set(low) == {Method.HYDROGEN_PEROXIDE, Method.ETHYLENE_OXIDE}
    assert not set(steam) & set(low)


def test_only_peroxide_refuses_cellulose() -> None:
    assert not Method.HYDROGEN_PEROXIDE.tolerates_cellulose
    for method in Method:
        if method is not Method.HYDROGEN_PEROXIDE:
            assert method.tolerates_cellulose


def test_low_temperature_methods_need_a_dry_load() -> None:
    assert not Method.HYDROGEN_PEROXIDE.tolerates_moisture
    assert not Method.ETHYLENE_OXIDE.tolerates_moisture
    assert Method.STEAM_PREVAC.tolerates_moisture


def test_only_ethylene_oxide_costs_aeration() -> None:
    assert Method.ETHYLENE_OXIDE.aeration == Duration.of_hours(12)
    assert Method.STEAM_PREVAC.aeration == Duration.zero()
    assert Method.HYDROGEN_PEROXIDE.aeration == Duration.zero()


def test_immediate_use_never_goes_to_a_shelf() -> None:
    assert not Method.STEAM_IUSS.may_be_stored
    assert Method.STEAM_PREVAC.may_be_stored


def test_nominals_are_the_textbook_numbers() -> None:
    assert Method.STEAM_PREVAC.nominal_temperature == Temperature(132.0)
    assert Method.STEAM_GRAVITY.nominal_exposure == Duration.of_minutes(30)
    assert Method.HYDROGEN_PEROXIDE.nominal_temperature == Temperature(50.0)


def test_a_nominal_profile_adds_dry_time_for_stored_steam() -> None:
    profile = MethodProfile.nominal(Method.STEAM_PREVAC)
    assert profile.dry_time == Duration.of_minutes(30)
    assert profile.total_cycle == Duration.of_minutes(34)


def test_immediate_use_gets_no_dry_time() -> None:
    assert MethodProfile.nominal(Method.STEAM_IUSS).dry_time == Duration.zero()


def test_a_dry_time_on_an_immediate_use_profile_is_refused() -> None:
    with pytest.raises(ValidationError):
        MethodProfile(
            Method.STEAM_IUSS,
            Temperature(132.0),
            Duration.of_minutes(4),
            Duration.of_minutes(1),
        )


def test_a_steam_profile_below_boiling_is_refused() -> None:
    with pytest.raises(ValidationError):
        MethodProfile(Method.STEAM_PREVAC, Temperature(80.0), Duration.of_minutes(4))


def test_a_profile_needs_an_exposure() -> None:
    with pytest.raises(ValidationError):
        MethodProfile(Method.HYDROGEN_PEROXIDE, Temperature(50.0), Duration.zero())


def test_aeration_lands_on_the_unavailable_time() -> None:
    profile = MethodProfile.nominal(Method.ETHYLENE_OXIDE)
    assert profile.unavailable_for == Duration.of_hours(13)


def test_a_steam_profile_is_unavailable_only_for_its_own_cycle() -> None:
    profile = MethodProfile.nominal(Method.STEAM_GRAVITY)
    assert profile.unavailable_for == profile.total_cycle


def test_describe_reads_like_a_cycle_card() -> None:
    profile = MethodProfile.nominal(Method.STEAM_PREVAC)
    assert profile.describe() == "steam, dynamic air removal at 132.0 C for 4m"
