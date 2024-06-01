from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.indicators.chemical import (
    ChemicalIndicator,
    ChemicalResult,
    IndicatorClass,
    Outcome,
    Placement,
)
from sterilot.methods import Method

DAY = date(2024, 6, 1)
READ_AT = datetime(2024, 6, 1, 10, 30)


def indicator(**changes: object) -> ChemicalIndicator:
    values: dict[str, object] = {
        "indicator_class": IndicatorClass.INTEGRATING,
        "lot": "ci 24b09",
        "expires_on": date(2025, 1, 31),
        "methods": frozenset({Method.STEAM_PREVAC, Method.STEAM_GRAVITY}),
    }
    values.update(changes)
    return ChemicalIndicator(**values)  # type: ignore[arg-type]


def result(**changes: object) -> ChemicalResult:
    values: dict[str, object] = {
        "indicator": indicator(),
        "placement": Placement.INTERNAL,
        "outcome": Outcome.PASS,
        "read_at": READ_AT,
        "read_by": "T-4471",
    }
    values.update(changes)
    return ChemicalResult(**values)  # type: ignore[arg-type]


def test_classes_are_numbered_and_labelled() -> None:
    assert IndicatorClass.numbered(5) is IndicatorClass.INTEGRATING
    assert IndicatorClass.numbered("class 6") is IndicatorClass.EMULATING
    assert IndicatorClass.INTEGRATING.number == 5
    assert IndicatorClass.PROCESS.label == "class 1 process indicator"
    with pytest.raises(ValidationError):
        IndicatorClass.numbered(9)


def test_only_a_process_indicator_is_external_only() -> None:
    assert IndicatorClass.PROCESS.external_only
    assert not IndicatorClass.PROCESS.may_go_inside
    assert IndicatorClass.SINGLE_VARIABLE.may_go_inside
    assert not IndicatorClass.SPECIFIC_TEST.may_go_inside


def test_only_five_and_six_stand_in_for_a_biological() -> None:
    stands = {cls for cls in IndicatorClass if cls.stands_in_for_a_biological}
    assert stands == {IndicatorClass.INTEGRATING, IndicatorClass.EMULATING}


def test_only_class_six_is_cycle_specific() -> None:
    assert IndicatorClass.EMULATING.cycle_specific
    assert not IndicatorClass.INTEGRATING.cycle_specific


def test_placement_and_outcome_lookup() -> None:
    assert Placement.named("challenge device") is Placement.CHALLENGE_DEVICE
    assert Outcome.named("FAIL") is Outcome.FAIL
    assert Outcome.PASS.acceptable
    with pytest.raises(ValidationError):
        Placement.named("somewhere")
    with pytest.raises(ValidationError):
        Outcome.named("maybe")


def test_an_indicator_is_made_for_a_method() -> None:
    with pytest.raises(ValidationError):
        indicator(methods=frozenset())


def test_an_emulating_indicator_names_its_cycle() -> None:
    with pytest.raises(ValidationError):
        indicator(indicator_class=IndicatorClass.EMULATING)
    made = indicator(indicator_class=IndicatorClass.EMULATING, cycle_name="prevac 132")
    assert made.cycle_name == "PREVAC-132"


def test_only_an_emulating_indicator_names_a_cycle() -> None:
    with pytest.raises(ValidationError):
        indicator(cycle_name="prevac 132")


def test_expiry() -> None:
    assert indicator().in_date_on(DAY)
    assert not indicator(expires_on=date(2024, 5, 1)).in_date_on(DAY)


def test_suitability_by_method() -> None:
    assert indicator().suits(Method.STEAM_PREVAC)
    assert not indicator().suits(Method.HYDROGEN_PEROXIDE)


def test_an_emulating_indicator_only_suits_its_own_cycle() -> None:
    made = indicator(indicator_class=IndicatorClass.EMULATING, cycle_name="PREVAC-132")
    assert made.suits(Method.STEAM_PREVAC, "prevac 132")
    assert not made.suits(Method.STEAM_PREVAC, "GRAVITY-121")
    assert not made.suits(Method.STEAM_PREVAC)


def test_a_process_indicator_cannot_go_inside() -> None:
    with pytest.raises(ValidationError):
        result(
            indicator=indicator(indicator_class=IndicatorClass.PROCESS),
            placement=Placement.INTERNAL,
        )


def test_a_good_reading_has_no_problems() -> None:
    assert result().passed
    assert result().problems(Method.STEAM_PREVAC, "PREVAC-132", DAY) == ()


def test_a_failed_strip_is_named_by_placement() -> None:
    problems = result(outcome=Outcome.FAIL).problems(Method.STEAM_PREVAC, "PREVAC-132", DAY)
    assert problems == ("the internal indicator failed",)


def test_an_unreadable_strip_is_its_own_problem() -> None:
    problems = result(outcome=Outcome.UNREADABLE).problems(Method.STEAM_PREVAC, "PREVAC-132", DAY)
    assert problems == ("the internal indicator could not be read",)


def test_an_expired_lot_is_named_with_its_date() -> None:
    old = result(indicator=indicator(expires_on=date(2024, 1, 31)))
    problems = old.problems(Method.STEAM_PREVAC, "PREVAC-132", DAY)
    assert problems[0] == "indicator lot CI-24B09 expired on 2024-01-31"


def test_an_indicator_used_in_the_wrong_method_is_named() -> None:
    problems = result().problems(Method.HYDROGEN_PEROXIDE, "VH2O2", DAY)
    assert "not made for vaporized hydrogen peroxide" in problems[0]


def test_an_emulating_indicator_in_the_wrong_cycle_is_named() -> None:
    made = indicator(indicator_class=IndicatorClass.EMULATING, cycle_name="PREVAC-132")
    problems = result(indicator=made).problems(Method.STEAM_PREVAC, "GRAVITY-121", DAY)
    assert problems[0] == "emulating indicator CI-24B09 is for PREVAC-132"


def test_describe_reads_like_the_log_line() -> None:
    assert str(result()) == "class 5 integrating internal pass"
