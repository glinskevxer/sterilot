from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.decon.cycle import Phase, PhaseRecord, PhaseSpec, Program, WasherCycle
from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import ValidationError
from sterilot.tolerance import Band
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

START = datetime(2024, 5, 1, 9, 0)


def washer(**changes: object) -> Washer:
    values: dict[str, object] = {
        "equipment": "WD-2",
        "model": "Reliance 444",
        "manufacturer": "Steris",
        "last_qualification": date(2024, 1, 10),
    }
    values.update(changes)
    return Washer(**values)  # type: ignore[arg-type]


def program(**changes: object) -> Program:
    specs = [
        PhaseSpec(Phase.PREWASH, Duration.of_minutes(2), Band.at_most(45.0, label="prewash")),
        PhaseSpec(
            Phase.WASH, Duration.of_minutes(5), Band.at_least(55.0, label="wash"), "enzymatic"
        ),
        PhaseSpec(Phase.RINSE, Duration.of_minutes(1)),
        PhaseSpec(Phase.THERMAL, Duration.of_minutes(5), Band.at_least(90.0, label="thermal")),
        PhaseSpec(Phase.DRY, Duration.of_minutes(10)),
    ]
    values: dict[str, object] = {"name": "instrument 1", "specs": specs}
    values.update(changes)
    return Program.of(**values)  # type: ignore[arg-type]


def good_phases() -> tuple[PhaseRecord, ...]:
    return (
        PhaseRecord(Phase.PREWASH, Duration.of_minutes(2), Temperature(38.0)),
        PhaseRecord(Phase.WASH, Duration.of_minutes(6), Temperature(60.0)),
        PhaseRecord(Phase.RINSE, Duration.of_minutes(1)),
        PhaseRecord(Phase.THERMAL, Duration.of_minutes(5), Temperature(91.0)),
        PhaseRecord(Phase.DRY, Duration.of_minutes(12)),
    )


def cycle(**changes: object) -> WasherCycle:
    values: dict[str, object] = {
        "equipment": "WD-2",
        "program": program(),
        "number": 4,
        "started_at": START,
        "operator": "T-4471",
        "phases": good_phases(),
        "trace": Trace.flat(START, 90.0, 300.0, step=30.0),
    }
    values.update(changes)
    return WasherCycle(**values)  # type: ignore[arg-type]


def test_phase_order_and_lookup() -> None:
    assert Phase.named("thermal") is Phase.THERMAL
    assert Phase.PREWASH.order < Phase.THERMAL.order
    with pytest.raises(ValidationError):
        Phase.named("soak")


def test_a_phase_spec_has_to_last() -> None:
    with pytest.raises(ValidationError):
        PhaseSpec(Phase.WASH, Duration.zero())


def test_a_program_needs_phases_in_order_and_without_repeats() -> None:
    with pytest.raises(ValidationError):
        Program.of("empty", [])
    with pytest.raises(ValidationError):
        Program.of("twice", [PhaseSpec(Phase.WASH, Duration.of_minutes(1))] * 2, a0_floor=None)
    with pytest.raises(ValidationError):
        Program.of(
            "backwards",
            [
                PhaseSpec(Phase.THERMAL, Duration.of_minutes(5)),
                PhaseSpec(Phase.WASH, Duration.of_minutes(5)),
            ],
        )


def test_an_a0_floor_needs_a_thermal_phase() -> None:
    with pytest.raises(ValidationError):
        Program.of("nothermal", [PhaseSpec(Phase.WASH, Duration.of_minutes(5))])


def test_an_a0_floor_needs_a_disinfecting_machine() -> None:
    with pytest.raises(ValidationError):
        Program.of(
            "ultra",
            [PhaseSpec(Phase.WASH, Duration.of_minutes(5))],
            washer_class=WasherClass.ULTRASONIC,
        )


def test_a_program_without_an_a0_floor_does_not_disinfect() -> None:
    ultrasonic = Program.of(
        "ultra",
        [PhaseSpec(Phase.WASH, Duration.of_minutes(5))],
        washer_class=WasherClass.ULTRASONIC,
        a0_floor=None,
    )
    assert not ultrasonic.disinfects
    assert ultrasonic.spec_for(Phase.THERMAL) is None


def test_a_clean_cycle_passes() -> None:
    assert cycle().passed(washer())
    assert cycle().failures(washer()) == ()


def test_cycle_numbers_start_at_one() -> None:
    with pytest.raises(ValidationError):
        cycle(number=0)


def test_a_cycle_judged_against_the_wrong_machine_is_refused() -> None:
    with pytest.raises(ValidationError):
        cycle().failures(washer(equipment="WD-9"))


def test_a_machine_past_qualification_fails_its_own_cycles() -> None:
    failures = cycle().failures(washer(last_qualification=date(2022, 1, 1)))
    assert "the machine is past its qualification date" in failures


def test_an_aborted_cycle_fails() -> None:
    assert "the cycle was aborted" in cycle(aborted=True).failures(washer())


def test_a_missing_phase_is_named() -> None:
    phases = tuple(record for record in good_phases() if record.phase is not Phase.THERMAL)
    failures = cycle(phases=phases).failures(washer())
    assert "the thermal phase did not run" in failures


def test_a_short_phase_names_the_gap() -> None:
    phases = tuple(
        PhaseRecord(Phase.WASH, Duration.of_minutes(3), Temperature(60.0))
        if record.phase is Phase.WASH
        else record
        for record in good_phases()
    )
    failures = cycle(phases=phases).failures(washer())
    assert "the wash phase was 2m short of 5m" in failures


def test_a_cold_thermal_phase_is_named_with_its_reading() -> None:
    phases = tuple(
        PhaseRecord(Phase.THERMAL, Duration.of_minutes(5), Temperature(84.0))
        if record.phase is Phase.THERMAL
        else record
        for record in good_phases()
    )
    failures = cycle(phases=phases).failures(washer())
    assert any("thermal: thermal 84.0 C is 6.0 C under" in item for item in failures)


def test_a_phase_with_no_temperature_where_one_is_specified_is_named() -> None:
    phases = tuple(
        PhaseRecord(Phase.THERMAL, Duration.of_minutes(5))
        if record.phase is Phase.THERMAL
        else record
        for record in good_phases()
    )
    failures = cycle(phases=phases).failures(washer())
    assert "the thermal phase has no temperature" in failures


def test_a_disinfecting_program_with_no_trace_cannot_be_scored() -> None:
    failures = cycle(trace=None).failures(washer())
    assert "the cycle has no trace to compute A0 from" in failures


def test_a_short_thermal_trace_fails_on_a0() -> None:
    weak = Trace.flat(START, 82.0, 200.0, step=20.0)
    failures = cycle(trace=weak).failures(washer())
    assert any(item.startswith("A0 ") for item in failures)


def test_the_a0_result_is_available_on_its_own() -> None:
    result = cycle().a0()
    assert result is not None
    assert result.passed
    assert cycle(trace=None).a0() is None


def test_a_program_written_for_another_class_of_machine_is_caught() -> None:
    tunnel = program(washer_class=WasherClass.TUNNEL)
    failures = cycle(program=tunnel).failures(washer())
    assert "the program is not written for that class of machine" in failures


def test_the_day_comes_off_the_start() -> None:
    assert cycle().day == date(2024, 5, 1)
    assert cycle().record_for(Phase.WASH) is not None
    assert cycle(phases=()).record_for(Phase.WASH) is None
