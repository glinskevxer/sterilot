from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.indicators.challenge import (
    AirRemovalTest,
    ChallengeKind,
    ChallengePack,
    qualifies_for_the_day,
    service_needed,
)
from sterilot.methods import Method
from sterilot.sterilizer.equipment import Sterilizer

DAY = date(2024, 6, 3)
MORNING = datetime(2024, 6, 3, 6, 40)


def chamber(**changes: object) -> Sterilizer:
    values: dict[str, object] = {
        "equipment": "AC-1",
        "model": "Amsco 400",
        "manufacturer": "Steris",
        "methods": frozenset({Method.STEAM_PREVAC}),
    }
    values.update(changes)
    return Sterilizer(**values)  # type: ignore[arg-type]


def pack(**changes: object) -> ChallengePack:
    values: dict[str, object] = {
        "kind": ChallengeKind.AIR_REMOVAL,
        "description": "disposable Bowie Dick pack",
        "methods": frozenset({Method.STEAM_PREVAC}),
        "lot": "bd 24f02",
    }
    values.update(changes)
    return ChallengePack(**values)  # type: ignore[arg-type]


def air_test(**changes: object) -> AirRemovalTest:
    values: dict[str, object] = {
        "equipment": "ac 1",
        "pack": pack(),
        "at": MORNING,
        "by": "T-4471",
        "passed": True,
    }
    values.update(changes)
    return AirRemovalTest(**values)  # type: ignore[arg-type]


def test_challenge_kinds() -> None:
    assert ChallengeKind.named("bowie dick") is ChallengeKind.AIR_REMOVAL
    assert ChallengeKind.named("PCD") is ChallengeKind.BIOLOGICAL
    assert ChallengeKind.AIR_REMOVAL.runs_empty
    assert not ChallengeKind.BIOLOGICAL.runs_empty
    with pytest.raises(ValidationError):
        ChallengeKind.named("packet")


def test_a_pack_needs_a_description_and_a_method() -> None:
    with pytest.raises(ValidationError):
        pack(description=" ")
    with pytest.raises(ValidationError):
        pack(methods=frozenset())


def test_an_air_removal_pack_is_a_steam_pack() -> None:
    with pytest.raises(ValidationError):
        pack(methods=frozenset({Method.HYDROGEN_PEROXIDE}))


def test_a_pack_lot_is_normalised_and_suitability_is_by_method() -> None:
    made = pack()
    assert made.lot == "BD-24F02"
    assert made.suits(Method.STEAM_PREVAC)
    assert not made.suits(Method.STEAM_GRAVITY)


def test_a_biological_pack_may_be_low_temperature() -> None:
    made = pack(kind=ChallengeKind.BIOLOGICAL, methods=frozenset({Method.HYDROGEN_PEROXIDE}))
    assert made.suits(Method.HYDROGEN_PEROXIDE)


def test_a_test_needs_an_air_removal_pack() -> None:
    with pytest.raises(ValidationError):
        air_test(pack=pack(kind=ChallengeKind.BIOLOGICAL))


def test_a_clean_test_has_no_problems() -> None:
    assert air_test().acceptable(chamber())
    assert air_test().equipment == "AC-1"
    assert air_test().day == DAY


def test_a_test_judged_against_another_chamber_is_refused() -> None:
    with pytest.raises(ValidationError):
        air_test().problems(chamber(equipment="AC-2"))


def test_a_gravity_chamber_owes_no_air_removal_test() -> None:
    gravity = chamber(methods=frozenset({Method.STEAM_GRAVITY}))
    problems = air_test().problems(gravity)
    assert "that chamber does not owe an air removal test" in problems


def test_a_loaded_chamber_invalidates_the_test() -> None:
    assert "the test ran with a load in the chamber" in air_test(chamber_empty=False).problems(
        chamber()
    )


def test_a_test_run_later_in_the_day_is_named() -> None:
    problems = air_test(first_run_of_day=False).problems(chamber())
    assert "the test was not the first run of the day" in problems


def test_a_failed_test_is_named() -> None:
    assert "the air removal test failed" in air_test(passed=False).problems(chamber())


def test_a_prevac_chamber_needs_a_clean_test_for_the_day() -> None:
    assert qualifies_for_the_day((air_test(),), chamber(), DAY)
    assert not qualifies_for_the_day((), chamber(), DAY)
    assert not qualifies_for_the_day((air_test(passed=False),), chamber(), DAY)


def test_a_test_from_yesterday_does_not_cover_today() -> None:
    yesterday = air_test(at=datetime(2024, 6, 2, 6, 40))
    assert not qualifies_for_the_day((yesterday,), chamber(), DAY)


def test_a_test_from_another_chamber_does_not_cover_this_one() -> None:
    other = air_test(equipment="AC-2")
    assert not qualifies_for_the_day((other,), chamber(), DAY)


def test_a_chamber_that_owes_no_test_qualifies_with_none() -> None:
    peroxide = chamber(methods=frozenset({Method.HYDROGEN_PEROXIDE}))
    assert qualifies_for_the_day((), peroxide, DAY)


def test_two_failures_in_a_row_call_for_service() -> None:
    first = air_test(at=datetime(2024, 6, 3, 6, 40), passed=False)
    second = air_test(at=datetime(2024, 6, 3, 7, 20), passed=False)
    assert not service_needed((first,), "AC-1")
    assert service_needed((first, second), "AC-1")


def test_a_pass_between_failures_resets_the_run() -> None:
    first = air_test(at=datetime(2024, 6, 3, 6, 40), passed=False)
    good = air_test(at=datetime(2024, 6, 3, 7, 0), passed=True)
    second = air_test(at=datetime(2024, 6, 3, 7, 20), passed=False)
    assert not service_needed((first, good, second), "AC-1")


def test_failures_on_another_chamber_do_not_count() -> None:
    first = air_test(at=datetime(2024, 6, 3, 6, 40), passed=False)
    other = air_test(at=datetime(2024, 6, 3, 6, 50), equipment="AC-2", passed=False)
    assert not service_needed((first, other), "AC-1")
