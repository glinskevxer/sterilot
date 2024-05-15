from __future__ import annotations

from datetime import date

import pytest

from sterilot.errors import ValidationError
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.sterilizer.equipment import (
    QUALIFICATION_RUNS_AFTER_REPAIR,
    ChamberSize,
    Sterilizer,
)

DAY = date(2024, 5, 1)


def steam(**changes: object) -> Sterilizer:
    values: dict[str, object] = {
        "equipment": "ac 1",
        "model": "Amsco 400",
        "manufacturer": "Steris",
        "methods": frozenset({Method.STEAM_PREVAC, Method.STEAM_IUSS}),
        "installed_on": date(2019, 6, 1),
    }
    values.update(changes)
    return Sterilizer(**values)  # type: ignore[arg-type]


def test_chamber_sizes() -> None:
    assert ChamberSize.named("double") is ChamberSize.DOUBLE
    assert ChamberSize.DOUBLE.sterilizer_units == 12
    assert ChamberSize.TABLETOP.sterilizer_units == 1
    with pytest.raises(ValidationError):
        ChamberSize.named("huge")


def test_identifiers_and_details() -> None:
    assert steam().equipment == "AC-1"
    with pytest.raises(ValidationError):
        steam(model=" ")
    with pytest.raises(ValidationError):
        steam(manufacturer="")


def test_a_sterilizer_runs_at_least_one_method() -> None:
    with pytest.raises(ValidationError):
        steam(methods=frozenset())


def test_no_chamber_mixes_steam_and_low_temperature() -> None:
    with pytest.raises(ValidationError):
        steam(methods=frozenset({Method.STEAM_PREVAC, Method.HYDROGEN_PEROXIDE}))


def test_negative_qualification_runs_are_refused() -> None:
    with pytest.raises(ValidationError):
        steam(qualification_runs_owed=-1)


def test_method_support() -> None:
    unit = steam()
    assert unit.supports(Method.STEAM_PREVAC)
    assert not unit.supports(Method.STEAM_GRAVITY)
    assert unit.refusal_for(Method.STEAM_GRAVITY, DAY) == (
        "this chamber does not run steam, gravity displacement"
    )


def test_only_a_prevac_chamber_owes_a_daily_air_removal_test() -> None:
    assert steam().daily_air_removal_test
    gravity = steam(methods=frozenset({Method.STEAM_GRAVITY}))
    assert not gravity.daily_air_removal_test
    assert not gravity.pulls_vacuum


def test_a_low_temperature_chamber_is_not_steam() -> None:
    peroxide = steam(methods=frozenset({Method.HYDROGEN_PEROXIDE}))
    assert not peroxide.is_steam
    assert peroxide.pulls_vacuum
    assert not peroxide.daily_air_removal_test


def test_capacity_comes_from_the_chamber() -> None:
    assert steam(chamber=ChamberSize.DOUBLE).capacity_units == 12


def test_a_healthy_chamber_may_run() -> None:
    assert steam().usable_on(DAY)
    assert steam().refusal_on(DAY) is None


def test_an_out_of_order_chamber_is_refused_first() -> None:
    unit = steam(out_of_order=True, qualification_runs_owed=3)
    assert unit.refusal_on(DAY) == "the sterilizer is out of order"


def test_a_retired_chamber_is_refused() -> None:
    unit = steam(in_service=DateRange(date(2019, 6, 1), date(2024, 1, 1)))
    assert unit.refusal_on(DAY) == "the sterilizer is not in service"


def test_a_chamber_not_yet_installed_is_refused() -> None:
    unit = steam(installed_on=date(2025, 1, 1))
    assert unit.refusal_on(DAY) == "the sterilizer was not installed yet"


def test_a_repair_puts_three_runs_on_the_chamber() -> None:
    unit = steam().repaired()
    assert unit.qualification_runs_owed == QUALIFICATION_RUNS_AFTER_REPAIR
    assert unit.refusal_on(DAY) == "the sterilizer owes 3 qualification runs"


def test_qualification_runs_count_down_one_at_a_time() -> None:
    unit = steam().repaired().qualification_run_passed().qualification_run_passed()
    assert unit.qualification_runs_owed == 1
    assert unit.refusal_on(DAY) == "the sterilizer owes 1 qualification run"
    assert unit.qualification_run_passed().usable_on(DAY)


def test_a_failed_qualification_run_restarts_the_count() -> None:
    unit = steam().repaired().qualification_run_passed().qualification_run_failed()
    assert unit.qualification_runs_owed == QUALIFICATION_RUNS_AFTER_REPAIR


def test_passing_a_run_that_is_not_owed_is_refused() -> None:
    with pytest.raises(ValidationError):
        steam().qualification_run_passed()


def test_changes_keep_every_other_field() -> None:
    unit = steam(notes="chamber 2", chamber=ChamberSize.DOUBLE).repaired()
    assert unit.notes == "chamber 2"
    assert unit.chamber is ChamberSize.DOUBLE
    assert unit.installed_on == date(2019, 6, 1)


def test_label() -> None:
    assert str(steam()) == "AC-1 Amsco 400"
