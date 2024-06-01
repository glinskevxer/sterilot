from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from sterilot.errors import ValidationError
from sterilot.indicators.biological import (
    BiologicalIndicator,
    BiologicalResult,
    Organism,
    Readout,
    verdict,
)
from sterilot.methods import Method

DAY = date(2024, 6, 1)
IN_AT = datetime(2024, 6, 1, 10, 0)


def vial(**changes: object) -> BiologicalIndicator:
    values: dict[str, object] = {
        "lot": "bi 24c11",
        "organism": Organism.STEAROTHERMOPHILUS,
        "readout": Readout.RAPID,
        "expires_on": date(2025, 3, 31),
    }
    values.update(changes)
    return BiologicalIndicator(**values)  # type: ignore[arg-type]


def reading(hours: float = 4.0, **changes: object) -> BiologicalResult:
    values: dict[str, object] = {
        "indicator": vial(),
        "started_at": IN_AT,
        "read_at": IN_AT + timedelta(hours=hours),
        "positive": False,
        "read_by": "T-4471",
    }
    values.update(changes)
    return BiologicalResult(**values)  # type: ignore[arg-type]


def control(hours: float = 4.0, **changes: object) -> BiologicalResult:
    values: dict[str, object] = {"positive": True, "is_control": True}
    values.update(changes)
    return reading(hours, **values)


def test_organisms_are_matched_to_methods() -> None:
    assert Organism.STEAROTHERMOPHILUS.challenges(Method.STEAM_PREVAC)
    assert Organism.STEAROTHERMOPHILUS.challenges(Method.HYDROGEN_PEROXIDE)
    assert not Organism.STEAROTHERMOPHILUS.challenges(Method.ETHYLENE_OXIDE)
    assert Organism.ATROPHAEUS.challenges(Method.ETHYLENE_OXIDE)


def test_organism_lookup() -> None:
    assert Organism.named("Geobacillus stearothermophilus") is Organism.STEAROTHERMOPHILUS
    assert Organism.named("atrophaeus") is Organism.ATROPHAEUS
    with pytest.raises(ValidationError):
        Organism.named("e coli")


def test_readout_windows() -> None:
    assert Readout.named("super rapid") is Readout.SUPER_RAPID
    assert Readout.RAPID.minimum.hours == pytest.approx(3.0)
    assert Readout.CONVENTIONAL.maximum.hours == pytest.approx(48.0)
    with pytest.raises(ValidationError):
        Readout.named("instant")


def test_an_indicator_carries_spores() -> None:
    with pytest.raises(ValidationError):
        vial(population_log=0.0)


def test_a_vial_cannot_be_read_before_it_goes_in() -> None:
    with pytest.raises(ValidationError):
        BiologicalResult(vial(), IN_AT, IN_AT - timedelta(hours=1), False, "T-4471")


def test_incubation_time_and_window() -> None:
    result = reading(hours=4)
    assert result.incubated_for.hours == pytest.approx(4.0)
    assert result.read_in_time
    assert not result.read_early


def test_a_vial_read_early_is_not_a_result() -> None:
    result = reading(hours=1)
    assert result.read_early
    assert not result.read_in_time
    assert result.problems(Method.STEAM_PREVAC, DAY) == ("the vial was read 2h early",)


def test_a_vial_read_after_the_window_is_stale() -> None:
    result = reading(hours=30)
    problems = result.problems(Method.STEAM_PREVAC, DAY)
    assert problems == ("the vial was read after the rapid window closed",)


def test_an_expired_lot_is_named() -> None:
    result = reading(indicator=vial(expires_on=date(2024, 1, 1)))
    assert "expired on 2024-01-01" in result.problems(Method.STEAM_PREVAC, DAY)[0]


def test_the_wrong_organism_for_the_method_is_named() -> None:
    problems = reading().problems(Method.ETHYLENE_OXIDE, DAY)
    assert problems[0] == "Geobacillus stearothermophilus does not challenge ethylene oxide"


def test_describe_reads_like_the_log() -> None:
    assert str(reading()) == "test BI-24C11 negative after 4h"
    assert str(control()) == "control BI-24C11 positive after 4h"


def test_a_clean_pair_passes() -> None:
    passed, problems = verdict(reading(), control(), Method.STEAM_PREVAC, DAY)
    assert passed
    assert problems == ()


def test_a_grown_test_vial_fails() -> None:
    passed, problems = verdict(reading(positive=True), control(), Method.STEAM_PREVAC, DAY)
    assert not passed
    assert "the biological indicator grew" in problems


def test_no_control_is_no_result() -> None:
    passed, problems = verdict(reading(), None, Method.STEAM_PREVAC, DAY)
    assert not passed
    assert problems == ("no control vial was incubated with this lot",)


def test_a_control_that_did_not_grow_invalidates_the_test() -> None:
    passed, problems = verdict(reading(), control(positive=False), Method.STEAM_PREVAC, DAY)
    assert not passed
    assert "the control did not grow, so the test proves nothing" in problems


def test_a_control_from_another_lot_is_named() -> None:
    other = control(indicator=vial(lot="BI-24C12"))
    passed, problems = verdict(reading(), other, Method.STEAM_PREVAC, DAY)
    assert not passed
    assert problems[0] == "the control is lot BI-24C12, the test is BI-24C11"


def test_a_control_read_outside_its_window_is_named() -> None:
    passed, problems = verdict(reading(), control(hours=1), Method.STEAM_PREVAC, DAY)
    assert not passed
    assert "the control was not read inside its own window" in problems


def test_a_control_passed_as_the_test_is_refused() -> None:
    with pytest.raises(ValidationError):
        verdict(control(), control(), Method.STEAM_PREVAC, DAY)


def test_a_test_vial_passed_as_the_control_is_refused() -> None:
    with pytest.raises(ValidationError):
        verdict(reading(), reading(), Method.STEAM_PREVAC, DAY)
