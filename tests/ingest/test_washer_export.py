from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.decon.cycle import Phase, PhaseSpec, Program
from sterilot.errors import ValidationError
from sterilot.ingest.washer_export import latest_start, load_washer_cycles
from sterilot.tolerance import Band
from sterilot.units.duration import Duration

EXPORT = """machine,cycle,program,started,operator,phase,seconds,peak_c
WD-2,318,INSTRUMENT-1,2024-10-21 06:40,T-4471,prewash,120,38.0
WD-2,318,INSTRUMENT-1,2024-10-21 06:40,T-4471,wash,360,60.0
WD-2,318,INSTRUMENT-1,2024-10-21 06:40,T-4471,thermal,300,91.0
WD-2,319,INSTRUMENT-1,2024-10-21 07:30,T-4471,wash,360,60.0
"""


def programs() -> dict[str, Program]:
    program = Program.of(
        "instrument 1",
        [
            PhaseSpec(Phase.PREWASH, Duration.of_minutes(2)),
            PhaseSpec(Phase.WASH, Duration.of_minutes(5), Band.at_least(55.0)),
            PhaseSpec(Phase.THERMAL, Duration.of_minutes(5), Band.at_least(90.0)),
        ],
    )
    return {program.name: program}


def test_rows_are_gathered_back_into_cycles() -> None:
    result = load_washer_cycles(EXPORT, programs())
    assert result.clean
    assert [cycle.number for cycle in result.cycles] == [318, 319]
    assert len(result.cycles[0].phases) == 3
    assert result.summary() == "2 cycles read, 0 rows rejected"


def test_the_cycle_carries_its_machine_and_operator() -> None:
    cycle = load_washer_cycles(EXPORT, programs()).cycles[0]
    assert cycle.equipment == "WD-2"
    assert cycle.operator == "T-4471"
    assert cycle.started_at == datetime(2024, 10, 21, 6, 40)


def test_phase_records_carry_their_peaks() -> None:
    cycle = load_washer_cycles(EXPORT, programs()).cycles[0]
    thermal = cycle.record_for(Phase.THERMAL)
    assert thermal is not None
    assert thermal.peak is not None
    assert thermal.peak.celsius == pytest.approx(91.0)
    assert thermal.ran_for.seconds == pytest.approx(300.0)


def test_a_missing_peak_is_allowed() -> None:
    text = EXPORT.replace(",thermal,300,91.0", ",thermal,300,")
    cycle = load_washer_cycles(text, programs()).cycles[0]
    thermal = cycle.record_for(Phase.THERMAL)
    assert thermal is not None
    assert thermal.peak is None


def test_an_unknown_program_is_reported_not_guessed() -> None:
    text = EXPORT.replace("INSTRUMENT-1", "INSTRUMENT-9")
    result = load_washer_cycles(text, programs())
    assert result.cycles == ()
    assert "names a program we do not have" in result.problems[0].describe()


def test_an_unreadable_phase_rejects_only_that_cycle() -> None:
    text = EXPORT.replace(",thermal,300,91.0", ",soak,300,91.0")
    result = load_washer_cycles(text, programs())
    assert [cycle.number for cycle in result.cycles] == [319]
    assert "will not build a cycle" in result.problems[0].describe()


def test_an_unreadable_timestamp_rejects_the_cycle() -> None:
    text = EXPORT.replace("2024-10-21 06:40", "last Tuesday")
    result = load_washer_cycles(text, programs())
    assert [cycle.number for cycle in result.cycles] == [319]


def test_a_short_row_is_rejected_and_the_rest_survive() -> None:
    text = EXPORT + "WD-2,320,INSTRUMENT-1\n"
    result = load_washer_cycles(text, programs())
    assert len(result.cycles) == 2
    assert not result.clean


def test_foreign_headers_are_aliased() -> None:
    text = EXPORT.replace(
        "machine,cycle,program,started,operator,phase,seconds,peak_c",
        "Washer,Cycle No,Program Name,Start Time,User,Step,Duration,Peak Temp",
    )
    result = load_washer_cycles(text, programs())
    assert len(result.cycles) == 2


def test_a_file_missing_a_required_column_is_refused() -> None:
    text = "machine,cycle\nWD-2,318\n"
    with pytest.raises(ValidationError):
        load_washer_cycles(text, programs())


def test_the_latest_start_is_where_the_next_read_begins() -> None:
    result = load_washer_cycles(EXPORT, programs())
    assert latest_start(result.cycles) == datetime(2024, 10, 21, 7, 30)
    assert latest_start(()) is None
