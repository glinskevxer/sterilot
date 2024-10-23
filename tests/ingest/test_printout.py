from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ingest.printout import parse_printout
from sterilot.units.temperature import Temperature

TAPE = """
STERIS AMSCO 400
STERILIZER    AC-1
CYCLE         PREVAC 132
CYCLE NO      0042
DATE 10/16/2024   TIME 08:14
OPERATOR      T-4471

PULSES        4
STER TEMP     133.4 C
STER TIME     04:02
DRY TIME      30:00
STER PRESS    29.6 PSIG
MAX TEMP      134.1 C
MIN TEMP      133.0 C
CYCLE COMPLETE
"""


def test_a_complete_tape_reads_its_identity() -> None:
    tape = parse_printout(TAPE)
    assert tape.equipment == "AC-1"
    assert tape.run == 42
    assert tape.operator == "T-4471"
    assert tape.cycle_name == "PREVAC 132"
    assert tape.started_at == datetime(2024, 10, 16, 8, 14)
    assert tape.complete
    assert not tape.aborted


def test_the_lot_control_number_falls_out_of_the_tape() -> None:
    assert parse_printout(TAPE).lot().format() == "AC-1-20241016-42"
    assert parse_printout(TAPE).lot().run_date == date(2024, 10, 16)


def test_the_measurements_come_out_in_the_right_units() -> None:
    measured = parse_printout(TAPE).measurements()
    assert measured.hold_temperature == Temperature(133.4)
    assert measured.exposure.seconds == pytest.approx(242.0)
    assert measured.dry_time.minutes == pytest.approx(30.0)
    assert measured.conditioning_pulses == 4
    assert measured.chamber_pressure is not None
    assert measured.chamber_pressure.psig == pytest.approx(29.6, abs=0.01)


def test_unrecognised_lines_are_left_alone() -> None:
    tape = parse_printout(TAPE)
    assert "max_temperature" in tape.values
    assert tape.values["max_temperature"] == "134.1 C"


def test_an_aborted_tape_carries_its_reason() -> None:
    text = TAPE.replace("CYCLE COMPLETE", "CYCLE ABORTED - DOOR SEAL")
    tape = parse_printout(text)
    assert tape.aborted
    assert tape.abort_reason == "DOOR SEAL"


def test_an_abort_with_no_reason_still_reads() -> None:
    text = TAPE.replace("CYCLE COMPLETE", "ABORTED")
    assert parse_printout(text).abort_reason == "no reason printed"


def test_a_tape_that_never_says_complete_is_treated_as_aborted() -> None:
    text = TAPE.replace("CYCLE COMPLETE", "")
    assert parse_printout(text).aborted


def test_an_empty_tape_is_refused() -> None:
    with pytest.raises(ValidationError):
        parse_printout("   ")


def test_a_tape_with_no_timestamp_is_refused() -> None:
    text = TAPE.replace("DATE 10/16/2024   TIME 08:14", "")
    with pytest.raises(ValidationError):
        parse_printout(text)


def test_a_tape_missing_a_field_names_it() -> None:
    text = TAPE.replace("OPERATOR      T-4471", "")
    with pytest.raises(ValidationError) as caught:
        parse_printout(text)
    assert caught.value.context["field"] == "operator"


def test_a_cycle_number_that_is_not_a_number_is_refused() -> None:
    text = TAPE.replace("CYCLE NO      0042", "CYCLE NO      FORTY TWO")
    with pytest.raises(ValidationError):
        parse_printout(text)


def test_a_tape_without_sterilize_lines_cannot_give_measurements() -> None:
    text = TAPE.replace("STER TEMP     133.4 C", "").replace("STER TIME     04:02", "")
    with pytest.raises(ValidationError):
        parse_printout(text).measurements()


def test_alternative_labels_are_understood() -> None:
    text = (
        TAPE.replace("STERILIZER    AC-1", "UNIT          AC-1")
        .replace("STER TEMP", "STERILIZE TEMP")
        .replace("STER TIME", "STERILIZE TIME")
        .replace("CYCLE NO      0042", "CYCLE #       0042")
    )
    tape = parse_printout(text)
    assert tape.equipment == "AC-1"
    assert tape.run == 42
    assert tape.measurements().hold_temperature == Temperature(133.4)


def test_pressure_in_other_units_is_read() -> None:
    for printed, expected in (("204.9 KPA", 204.9), ("2.05 BAR", 205.0), ("44.1 PSIA", 304.1)):
        text = TAPE.replace("STER PRESS    29.6 PSIG", f"STER PRESS    {printed}")
        measured = parse_printout(text).measurements()
        assert measured.chamber_pressure is not None
        assert measured.chamber_pressure.kilopascals == pytest.approx(expected, rel=0.01)


def test_an_unreadable_pressure_is_refused() -> None:
    text = TAPE.replace("STER PRESS    29.6 PSIG", "STER PRESS    HIGH")
    with pytest.raises(ValidationError):
        parse_printout(text).measurements()


def test_a_run_number_below_one_is_refused() -> None:
    text = TAPE.replace("CYCLE NO      0042", "CYCLE NO      0000")
    with pytest.raises(ValidationError):
        parse_printout(text)
