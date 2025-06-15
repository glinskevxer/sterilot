from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main

TAPE = """
STERILIZER    AC-1
CYCLE         PREVAC 132
CYCLE NO      0042
DATE 01/06/2025   TIME 08:14
OPERATOR      T-4471
PULSES        4
STER TEMP     133.4 C
STER TIME     04:02
DRY TIME      30:00
CYCLE COMPLETE
"""


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "sterilot.sqlite3")
    run(
        path,
        "machine",
        "add-sterilizer",
        "AC-1",
        "--model",
        "Amsco 400",
        "--manufacturer",
        "Steris",
        "--method",
        "prevac",
    )
    return path


def run(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, "--badge", "T-4471", *args])


def record(db: str, *extra: str) -> Result:
    return run(
        db,
        "cycle",
        "record",
        "--equipment",
        "AC-1",
        "--method",
        "prevac",
        "--started",
        "2025-01-06 08:14",
        "--temp",
        "133.4C",
        "--exposure",
        "4",
        "--dry",
        "31",
        "--pulses",
        "4",
        *extra,
    )


def test_a_cycle_records_and_takes_the_next_run_number(db: str) -> None:
    first = record(db)
    assert first.exit_code == 0
    assert "recorded AC-1-20250106-01" in first.output
    second = record(db)
    assert "recorded AC-1-20250106-02" in second.output


def test_an_explicit_run_number_is_used(db: str) -> None:
    result = record(db, "--run", "7")
    assert "AC-1-20250106-07" in result.output


def test_a_cycle_can_be_read_back(db: str) -> None:
    record(db)
    result = run(db, "cycle", "show", "AC-1-20250106-01")
    assert result.exit_code == 0
    assert "133.4 C" in result.output
    assert "4m" in result.output
    assert "aborted" in result.output


def test_an_unknown_lot_exits_not_found(db: str) -> None:
    result = run(db, "cycle", "show", "AC-1-20250106-09")
    assert result.exit_code == 3


def test_an_aborted_cycle_carries_its_reason(db: str) -> None:
    record(db, "--aborted", "door seal")
    result = run(db, "cycle", "show", "AC-1-20250106-01")
    assert "door seal" in result.output


def test_a_pressure_is_read_in_whatever_unit_is_given(db: str) -> None:
    record(db, "--pressure", "29.6 psig")
    result = run(db, "cycle", "check", "AC-1-20250106-01")
    assert result.exit_code == 0
    assert "acceptable" in result.output


def test_a_cold_cycle_fails_the_check(db: str) -> None:
    record(db, "--temp", "126C")
    result = run(db, "cycle", "check", "AC-1-20250106-01")
    assert result.exit_code == 5
    assert "chamber 126.0 C" in result.output


def test_a_day_lists_the_runs(db: str) -> None:
    record(db)
    record(db)
    result = run(db, "cycle", "day", "AC-1", "--on", "2025-01-06")
    assert result.exit_code == 0
    assert "AC-1-20250106-01" in result.output
    assert "AC-1-20250106-02" in result.output


def test_a_tape_can_be_read_from_a_file(db: str, tmp_path: Path) -> None:
    tape = tmp_path / "tape.txt"
    tape.write_text(TAPE, encoding="utf-8")
    result = run(db, "cycle", "read-tape", str(tape))
    assert result.exit_code == 0
    assert "recorded AC-1-20250106-42" in result.output
    shown = run(db, "cycle", "show", "AC-1-20250106-42")
    assert "133.4 C" in shown.output


def test_an_unreadable_tape_is_a_validation_failure(db: str, tmp_path: Path) -> None:
    tape = tmp_path / "tape.txt"
    tape.write_text("nothing useful here\n", encoding="utf-8")
    result = run(db, "cycle", "read-tape", str(tape))
    assert result.exit_code == 2


def test_recording_without_a_badge_is_refused(tmp_path: Path) -> None:
    path = str(tmp_path / "sterilot.sqlite3")
    result = CliRunner().invoke(
        main,
        [
            "--db",
            path,
            "cycle",
            "record",
            "--equipment",
            "AC-1",
            "--method",
            "prevac",
            "--started",
            "2025-01-06 08:14",
            "--temp",
            "133.4C",
            "--exposure",
            "4",
        ],
    )
    assert result.exit_code == 7


TRACE = """offset,temperature
0,100.0
60,134.0
300,134.0
360,110.0
"""


def test_a_trace_file_is_scored(db: str, tmp_path: Path) -> None:
    path = tmp_path / "trace.csv"
    path.write_text(TRACE, encoding="utf-8")
    result = run(db, "cycle", "trace", str(path))
    assert result.exit_code == 0
    assert "F0" in result.output
    assert "clears" in result.output
    assert "log reductions" in result.output


def test_a_weak_trace_exits_with_the_policy_status(db: str, tmp_path: Path) -> None:
    path = tmp_path / "trace.csv"
    path.write_text(TRACE.replace("134.0", "115.0"), encoding="utf-8")
    result = run(db, "cycle", "trace", str(path))
    assert result.exit_code == 5
    assert "short" in result.output


def test_a_file_with_no_usable_trace_exits_two(db: str, tmp_path: Path) -> None:
    path = tmp_path / "trace.csv"
    path.write_text("offset,temperature\n0,100.0\n", encoding="utf-8")
    result = run(db, "cycle", "trace", str(path))
    assert result.exit_code == 2
    assert "no trace read" in result.output
