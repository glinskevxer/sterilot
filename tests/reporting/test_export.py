from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.reporting import export
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

DAY = date(2025, 6, 2)
START = datetime(2025, 6, 2, 8, 0)


def cycle(run: int = 1, aborted: bool = False) -> SterilizerCycle:
    return SterilizerCycle(
        LotControlNumber("AC-1", DAY, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        START,
        "T-4471",
        CycleMeasurements(Temperature(133.4), Duration.of_minutes(4), Duration.of_minutes(31)),
        aborted=aborted,
        abort_reason="door seal" if aborted else "",
    )


def record(kind: ReleaseKind | None = ReleaseKind.ROUTINE) -> LoadRecord:
    load = Load(
        "LD-1",
        Method.STEAM_PREVAC,
        (LoadItem("ORT-0114", "ORT-MAJOR"), LoadItem("ORT-0115", "ORT-MAJOR")),
        "T-4471",
        START,
    )
    made = LoadRecord(load, cycle())
    if kind is None:
        return made
    return made.decided(ReleaseDecision(kind, ("a reason", "another"), START, "T-9002"))


def entry() -> Nonconformance:
    return Nonconformance(
        "NC-1", Category.STERILIZATION, Severity.MINOR, START, "T-4471", "wet pack", "AC-1"
    )


def test_a_header_is_always_written() -> None:
    text = export.write(("a", "b"), [])
    assert text == "a,b\n"


def test_rows_follow_the_header() -> None:
    text = export.write(("a", "b"), [[1, 2], [3, 4]])
    assert text.splitlines() == ["a,b", "1,2", "3,4"]


def test_nothing_is_written_for_a_none() -> None:
    assert export.write(("a", "b"), [[None, 1]]).splitlines()[1] == ",1"


def test_a_row_that_does_not_match_is_refused() -> None:
    with pytest.raises(ValidationError):
        export.write(("a", "b"), [[1]])


def test_columns_are_required() -> None:
    with pytest.raises(ValidationError):
        export.write((), [])


def test_another_delimiter_can_be_asked_for() -> None:
    assert export.write(("a", "b"), [[1, 2]], delimiter="\t").splitlines()[0] == "a\tb"


def test_a_value_with_a_comma_is_quoted() -> None:
    text = export.write(("a",), [["one, two"]])
    assert text.splitlines()[1] == '"one, two"'


def test_cycles_export_with_iso_dates() -> None:
    text = export.cycles([cycle()])
    lines = text.splitlines()
    assert lines[0].startswith("lot,sterilizer,run_date")
    assert "AC-1-20250602-01" in lines[1]
    assert "2025-06-02" in lines[1]
    assert "2025-06-02T08:00:00" in lines[1]
    assert lines[1].endswith(",no")


def test_an_aborted_cycle_says_yes() -> None:
    assert export.cycles([cycle(aborted=True)]).splitlines()[1].endswith(",yes")


def test_loads_export_with_their_trays_and_reasons() -> None:
    text = export.loads([record()])
    line = text.splitlines()[1]
    assert "LD-1" in line
    assert "ORT-0114 ORT-0115" in line
    assert "a reason; another" in line
    assert "T-9002" in line


def test_an_undecided_load_leaves_the_decision_columns_empty() -> None:
    line = export.loads([record(kind=None)]).splitlines()[1]
    assert line.endswith(",")
    assert "pending" in line


def test_exceptions_export_with_their_due_date() -> None:
    line = export.exceptions([entry()]).splitlines()[1]
    assert "NC-1" in line
    assert "2025-06-16" in line
    assert "wet pack" in line


def test_a_closed_exception_carries_its_closure() -> None:
    closed = entry().closed(datetime(2025, 6, 4, 9, 0), "T-9002")
    line = export.exceptions([closed]).splitlines()[1]
    assert "2025-06-04T09:00:00" in line
    assert line.endswith("wet pack")


def test_an_empty_export_is_just_the_header() -> None:
    assert export.loads([]).splitlines() == [",".join(export.LOAD_COLUMNS)]
