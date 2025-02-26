from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import add_washer, invoke

EXPORT = """machine,cycle,program,started,operator,phase,seconds,peak_c
WD-2,318,INSTRUMENT-1,2025-02-27 06:40,T-4471,prewash,120,38.0
WD-2,318,INSTRUMENT-1,2025-02-27 06:40,T-4471,wash,360,60.0
WD-2,318,INSTRUMENT-1,2025-02-27 06:40,T-4471,rinse,60,
WD-2,318,INSTRUMENT-1,2025-02-27 06:40,T-4471,thermal,300,91.0
WD-2,318,INSTRUMENT-1,2025-02-27 06:40,T-4471,dry,660,
"""


@pytest.fixture
def decon(db: str) -> str:
    add_washer(db)
    invoke(db, "wash", "seed-standard")
    return db


def test_the_standard_program_is_created_on_request(db: str) -> None:
    add_washer(db)
    result = invoke(db, "wash", "seed-standard")
    assert result.exit_code == 0
    assert "INSTRUMENT-1 has 5 phases" in result.output


def test_programs_are_listed(decon: str) -> None:
    result = invoke(decon, "wash", "programs")
    assert "INSTRUMENT-1" in result.output
    assert "thermal" in result.output


def test_an_empty_department_says_so(db: str) -> None:
    result = invoke(db, "wash", "programs")
    assert "no programs defined" in result.output


def test_a_cycle_records_and_checks_clean(decon: str) -> None:
    recorded = invoke(
        decon,
        "wash",
        "record",
        "--equipment",
        "WD-2",
        "--program",
        "INSTRUMENT-1",
        "--number",
        "318",
        "--started",
        "2025-02-27 06:40",
        "--phase",
        "prewash=120:38C",
        "--phase",
        "wash=360:60C",
        "--phase",
        "rinse=60",
        "--phase",
        "thermal=300:91C",
        "--phase",
        "dry=660",
    )
    assert recorded.exit_code == 0
    assert "recorded WD-2 cycle 318" in recorded.output
    checked = invoke(
        decon,
        "wash",
        "check",
        "--equipment",
        "WD-2",
        "--number",
        "318",
        "--started",
        "2025-02-27 06:40",
    )
    assert checked.exit_code == 5
    assert "no trace to compute A0" in checked.output


def test_a_short_phase_is_named_by_the_check(decon: str) -> None:
    invoke(
        decon,
        "wash",
        "record",
        "--equipment",
        "WD-2",
        "--program",
        "INSTRUMENT-1",
        "--number",
        "319",
        "--started",
        "2025-02-27 07:40",
        "--phase",
        "wash=60:60C",
        "--phase",
        "thermal=300:91C",
    )
    result = invoke(
        decon,
        "wash",
        "check",
        "--equipment",
        "WD-2",
        "--number",
        "319",
        "--started",
        "2025-02-27 07:40",
    )
    assert result.exit_code == 5
    assert "the wash phase was 4m short of 5m" in result.output
    assert "the prewash phase did not run" in result.output


def test_the_day_lists_the_cycles(decon: str) -> None:
    invoke(
        decon,
        "wash",
        "record",
        "--equipment",
        "WD-2",
        "--program",
        "INSTRUMENT-1",
        "--number",
        "318",
        "--started",
        "2025-02-27 06:40",
        "--phase",
        "wash=360:60C",
    )
    result = invoke(decon, "wash", "day", "WD-2", "--on", "2025-02-27")
    assert "318" in result.output
    assert "INSTRUMENT-1" in result.output


def test_an_export_file_is_imported(decon: str, tmp_path: Path) -> None:
    path = tmp_path / "export.csv"
    path.write_text(EXPORT, encoding="utf-8")
    result = invoke(decon, "wash", "import", str(path))
    assert result.exit_code == 0
    assert "1 cycles read, 0 rows rejected" in result.output
    listed = invoke(decon, "wash", "day", "WD-2", "--on", "2025-02-27")
    assert "318" in listed.output


def test_an_export_with_a_bad_row_reports_it(decon: str, tmp_path: Path) -> None:
    path = tmp_path / "export.csv"
    path.write_text(EXPORT + "WD-2,320,INSTRUMENT-1\n", encoding="utf-8")
    result = invoke(decon, "wash", "import", str(path))
    assert result.exit_code == 2
    assert "wrong number of fields" in result.output


def test_importing_with_no_programs_is_refused(db: str, tmp_path: Path) -> None:
    add_washer(db)
    path = tmp_path / "export.csv"
    path.write_text(EXPORT, encoding="utf-8")
    result = invoke(db, "wash", "import", str(path))
    assert result.exit_code != 0
    assert "no wash programs" in result.output


def test_the_a0_calculator_scores_a_flat_hold(decon: str) -> None:
    result = invoke(decon, "wash", "a0", "--celsius", "90", "--minutes", "5")
    assert result.exit_code == 0
    assert "3000" in result.output
    assert "clears" in result.output


def test_a_cold_hold_falls_short(decon: str) -> None:
    result = invoke(decon, "wash", "a0", "--celsius", "76", "--minutes", "5")
    assert "short" in result.output
