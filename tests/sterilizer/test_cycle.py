from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle, next_run_number, runs_on
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.pressure import saturation_pressure
from sterilot.units.temperature import Temperature

DAY = date(2024, 6, 20)
START = datetime(2024, 6, 20, 8, 15)


def chamber(**changes: object) -> Sterilizer:
    values: dict[str, object] = {
        "equipment": "AC-1",
        "model": "Amsco 400",
        "manufacturer": "Steris",
        "methods": frozenset({Method.STEAM_PREVAC}),
    }
    values.update(changes)
    return Sterilizer(**values)  # type: ignore[arg-type]


def measured(**changes: object) -> CycleMeasurements:
    values: dict[str, object] = {
        "hold_temperature": Temperature(133.0),
        "exposure": Duration.of_minutes(4),
        "dry_time": Duration.of_minutes(31),
        "chamber_pressure": saturation_pressure(Temperature(133.0)),
        "conditioning_pulses": 4,
    }
    values.update(changes)
    return CycleMeasurements(**values)  # type: ignore[arg-type]


def cycle(**changes: object) -> SterilizerCycle:
    values: dict[str, object] = {
        "lot": LotControlNumber("AC-1", DAY, 2),
        "spec": CycleSpec.standard(Method.STEAM_PREVAC),
        "started_at": START,
        "operator": "T-4471",
        "measurements": measured(),
        "trace": Trace.flat(START, 133.0, 240.0, step=20.0),
    }
    values.update(changes)
    return SterilizerCycle(**values)  # type: ignore[arg-type]


def test_the_lot_number_has_to_match_the_day() -> None:
    with pytest.raises(ValidationError):
        cycle(lot=LotControlNumber("AC-1", date(2024, 6, 19), 2))


def test_an_aborted_cycle_records_why() -> None:
    with pytest.raises(ValidationError):
        cycle(aborted=True)
    with pytest.raises(ValidationError):
        cycle(abort_reason="door seal")


def test_an_f0_floor_is_positive() -> None:
    with pytest.raises(ValidationError):
        cycle(f0_floor=0.0)


def test_the_cycle_reads_its_identity_off_the_lot_number() -> None:
    run = cycle()
    assert run.equipment == "AC-1"
    assert run.day == DAY
    assert run.run == 2
    assert run.method is Method.STEAM_PREVAC
    assert str(run) == "AC-1-20240620-02"


def test_a_clean_cycle_passes() -> None:
    assert cycle().acceptable(chamber())
    assert cycle().failures(chamber()) == ()


def test_a_cycle_judged_against_the_wrong_chamber_is_refused() -> None:
    with pytest.raises(ValidationError):
        cycle().failures(chamber(equipment="AC-2"))


def test_a_chamber_that_does_not_run_the_method_is_named() -> None:
    gravity = chamber(methods=frozenset({Method.STEAM_GRAVITY}))
    failures = cycle().failures(gravity)
    assert failures[0] == "this chamber does not run steam, dynamic air removal"


def test_a_chamber_owing_qualification_runs_fails_its_cycles() -> None:
    failures = cycle().failures(chamber().repaired())
    assert "the sterilizer owes 3 qualification runs" in failures


def test_an_aborted_cycle_says_so_with_its_reason() -> None:
    failures = cycle(aborted=True, abort_reason="door seal").failures(chamber())
    assert "the cycle was aborted: door seal" in failures


def test_a_missing_air_removal_test_fails_the_cycle() -> None:
    failures = cycle().failures(chamber(), air_removal_ok=False)
    assert "the chamber had no passing air removal test that day" in failures


def test_parameter_failures_come_through() -> None:
    cold = cycle(measurements=measured(hold_temperature=Temperature(128.0)))
    assert any("chamber 128.0 C" in item for item in cold.failures(chamber()))
    assert cold.parameter_failures()


def test_f0_is_computed_for_a_steam_cycle_with_a_trace() -> None:
    result = cycle().f0()
    assert result is not None
    assert result.passed


def test_a_cycle_with_no_trace_has_no_f0() -> None:
    assert cycle(trace=None).f0() is None


def test_a_low_temperature_cycle_has_no_f0() -> None:
    peroxide = cycle(
        spec=CycleSpec.standard(Method.HYDROGEN_PEROXIDE),
        measurements=CycleMeasurements(Temperature(50.0), Duration.of_minutes(30)),
    )
    assert peroxide.f0() is None


def test_a_weak_steam_cycle_fails_on_f0() -> None:
    weak = cycle(trace=Trace.flat(START, 118.0, 200.0, step=20.0))
    assert any(item.startswith("F0") for item in weak.failures(chamber()))


def test_the_contents_are_unavailable_until_the_cycle_and_aeration_are_done() -> None:
    run = cycle()
    assert run.unavailable_until == datetime(2024, 6, 20, 8, 50)


def test_ethylene_oxide_adds_twelve_hours_before_anything_can_be_touched() -> None:
    eo = SterilizerCycle(
        LotControlNumber("EO-1", DAY, 1),
        CycleSpec.standard(Method.ETHYLENE_OXIDE),
        START,
        "T-4471",
        CycleMeasurements(Temperature(55.0), Duration.of_hours(1)),
    )
    assert eo.unavailable_until == datetime(2024, 6, 20, 21, 15)


def test_runs_on_filters_and_orders_by_run_number() -> None:
    first = cycle(lot=LotControlNumber("AC-1", DAY, 1))
    second = cycle(lot=LotControlNumber("AC-1", DAY, 3))
    other = cycle(lot=LotControlNumber("AC-2", DAY, 1))
    found = runs_on((second, other, first), "AC-1", DAY)
    assert [item.run for item in found] == [1, 3]


def test_next_run_number_follows_the_last_one() -> None:
    assert next_run_number((), "AC-1", DAY) == 1
    runs = (
        cycle(lot=LotControlNumber("AC-1", DAY, 1)),
        cycle(lot=LotControlNumber("AC-1", DAY, 4)),
    )
    assert next_run_number(runs, "AC-1", DAY) == 5
    assert next_run_number(runs, "AC-2", DAY) == 1
