from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.methods import Method
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.tolerance import Band
from sterilot.units.duration import Duration
from sterilot.units.pressure import Pressure, saturation_pressure
from sterilot.units.temperature import Temperature


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


def test_a_standard_cycle_exists_for_every_method() -> None:
    for method in Method:
        spec = CycleSpec.standard(method)
        assert spec.method is method
        assert spec.exposure.seconds > 0


def test_the_prevac_standard_counts_pulses() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    assert spec.conditioning_pulses == 3
    assert spec.name == "PREVAC-132"


def test_the_immediate_use_standard_has_no_dry_time() -> None:
    assert CycleSpec.standard(Method.STEAM_IUSS).dry_time == Duration.zero()


def test_low_temperature_standards_carry_no_superheat_limit() -> None:
    assert CycleSpec.standard(Method.HYDROGEN_PEROXIDE).superheat_limit is None
    assert CycleSpec.standard(Method.ETHYLENE_OXIDE).superheat_limit is None


def test_a_cycle_needs_an_exposure_and_a_floor() -> None:
    with pytest.raises(ValidationError):
        CycleSpec("x", Method.STEAM_PREVAC, Band.between(132.0, 135.0), Duration.zero())
    with pytest.raises(ValidationError):
        CycleSpec("x", Method.STEAM_PREVAC, Band.at_most(135.0), Duration.of_minutes(4))


def test_superheat_is_meaningless_outside_steam() -> None:
    with pytest.raises(ValidationError):
        CycleSpec(
            "x",
            Method.HYDROGEN_PEROXIDE,
            Band.between(45.0, 55.0),
            Duration.of_minutes(28),
            superheat_limit=3.0,
        )


def test_only_a_prevac_cycle_counts_pulses() -> None:
    with pytest.raises(ValidationError):
        CycleSpec(
            "x",
            Method.STEAM_GRAVITY,
            Band.between(121.0, 124.0),
            Duration.of_minutes(30),
            conditioning_pulses=3,
        )


def test_an_immediate_use_cycle_cannot_carry_dry_time() -> None:
    with pytest.raises(ValidationError):
        CycleSpec(
            "x",
            Method.STEAM_IUSS,
            Band.between(132.0, 135.0),
            Duration.of_minutes(4),
            Duration.of_minutes(5),
        )


def test_negative_pulses_are_refused() -> None:
    with pytest.raises(ValidationError):
        measured(conditioning_pulses=-1)


def test_a_good_run_passes_every_parameter() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    assert spec.accepts(measured())
    assert spec.failures(measured()) == ()
    assert len(spec.readings(measured())) == 5


def test_a_cold_chamber_is_named_with_its_reading() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    failures = spec.failures(measured(hold_temperature=Temperature(130.0)))
    assert any("chamber 130.0 C is 2.0 C under" in item for item in failures)


def test_a_short_exposure_is_named() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    failures = spec.failures(measured(exposure=Duration.of_minutes(3)))
    assert any(item.startswith("exposure 180.0 s") for item in failures)


def test_a_short_dry_time_is_named() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    failures = spec.failures(measured(dry_time=Duration.of_minutes(10)))
    assert any(item.startswith("dry time") for item in failures)


def test_too_few_pulses_are_named() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    failures = spec.failures(measured(conditioning_pulses=2))
    assert any(item.startswith("pulses 2.0") for item in failures)


def test_a_missing_pulse_count_reads_as_none_at_all() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    failures = spec.failures(measured(conditioning_pulses=None))
    assert any(item.startswith("pulses 0.0") for item in failures)


def test_superheated_steam_is_caught() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    hot = measured(
        hold_temperature=Temperature(134.0),
        chamber_pressure=saturation_pressure(Temperature(125.0)),
    )
    failures = spec.failures(hot)
    assert any(item.startswith("superheat") for item in failures)


def test_wet_steam_passes_the_superheat_check() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    wet = measured(
        hold_temperature=Temperature(133.0),
        chamber_pressure=saturation_pressure(Temperature(134.0)),
    )
    assert spec.accepts(wet)


def test_a_steam_run_with_no_pressure_cannot_rule_out_superheat() -> None:
    spec = CycleSpec.standard(Method.STEAM_PREVAC)
    failures = spec.failures(measured(chamber_pressure=None))
    assert "no chamber pressure, so superheat cannot be ruled out" in failures


def test_a_peroxide_run_needs_no_pressure() -> None:
    spec = CycleSpec.standard(Method.HYDROGEN_PEROXIDE)
    run = CycleMeasurements(Temperature(50.0), Duration.of_minutes(30))
    assert spec.accepts(run)


def test_the_gravity_standard_wants_thirty_minutes() -> None:
    spec = CycleSpec.standard(Method.STEAM_GRAVITY)
    short = CycleMeasurements(
        Temperature(122.0),
        Duration.of_minutes(20),
        Duration.of_minutes(31),
        Pressure.from_kpa_absolute(saturation_pressure(Temperature(122.0)).kilopascals),
    )
    assert not spec.accepts(short)
