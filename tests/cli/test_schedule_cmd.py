from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import invoke


@pytest.fixture
def theatre(db: str) -> str:
    invoke(
        db,
        "schedule",
        "add-card",
        "PC-118",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "total knee revision",
        "--line",
        "ORT-MAJOR=2",
        "--line",
        "GEN-MINOR=1:preferred",
        "--from",
        "2025-01-01",
    )
    invoke(
        db,
        "schedule",
        "add-case",
        "OR3-01",
        "--room",
        "OR3",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "total knee revision",
        "--start",
        "2025-04-17 08:00",
        "--minutes",
        "120",
        "--card",
        "PC-118",
    )
    return db


def test_a_card_is_written(db: str) -> None:
    result = invoke(
        db,
        "schedule",
        "add-card",
        "PC-118",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--line",
        "ORT-MAJOR=2",
        "--from",
        "2025-01-01",
    )
    assert result.exit_code == 0
    assert "calls for 2 sets" in result.output


def test_a_case_goes_on_the_list(theatre: str) -> None:
    result = invoke(
        theatre,
        "schedule",
        "add-case",
        "OR4-01",
        "--room",
        "OR4",
        "--surgeon",
        "Bell",
        "--procedure",
        "cystoscopy",
        "--start",
        "2025-04-17 09:00",
        "--minutes",
        "45",
    )
    assert result.exit_code == 0
    assert "OR4-01 09:00 OR4 Bell cystoscopy (45 min)" in result.output


def test_a_case_with_no_time_is_refused(theatre: str) -> None:
    result = invoke(
        theatre,
        "schedule",
        "add-case",
        "OR4-01",
        "--room",
        "OR4",
        "--surgeon",
        "Bell",
        "--procedure",
        "cystoscopy",
        "--start",
        "2025-04-17 09:00",
        "--minutes",
        "0",
    )
    assert result.exit_code == 2


def test_the_day_lists_the_cases(theatre: str) -> None:
    result = invoke(theatre, "schedule", "day", "--on", "2025-04-17")
    assert result.exit_code == 0
    assert "OR3-01" in result.output
    assert "Okonkwo" in result.output
    assert "PC-118" in result.output


def test_a_double_booked_room_is_reported(theatre: str) -> None:
    invoke(
        theatre,
        "schedule",
        "add-case",
        "OR3-02",
        "--room",
        "OR3",
        "--surgeon",
        "Bell",
        "--procedure",
        "cystoscopy",
        "--start",
        "2025-04-17 09:00",
        "--minutes",
        "45",
    )
    result = invoke(theatre, "schedule", "day", "--on", "2025-04-17")
    assert "OR3-01 and OR3-02 share OR3" in result.output


def test_the_demand_shows_what_is_short(theatre: str) -> None:
    result = invoke(theatre, "schedule", "demand", "--on", "2025-04-17")
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.startswith("ORT-MAJOR")]
    assert lines[0].split()[-1] == "2"


def test_a_case_with_no_card_is_named_in_the_demand(theatre: str) -> None:
    invoke(
        theatre,
        "schedule",
        "add-case",
        "OR4-01",
        "--room",
        "OR4",
        "--surgeon",
        "Bell",
        "--procedure",
        "cystoscopy",
        "--start",
        "2025-04-17 09:00",
        "--minutes",
        "45",
    )
    result = invoke(theatre, "schedule", "demand", "--on", "2025-04-17")
    assert "OR4-01 has no preference card" in result.output


def test_a_case_reads_back_with_its_card(theatre: str) -> None:
    result = invoke(theatre, "schedule", "case", "OR3-01")
    assert result.exit_code == 0
    assert "trays due" in result.output
    assert "07:00" in result.output
    assert "2 x ORT-MAJOR (essential)" in result.output
    assert "1 x GEN-MINOR (preferred)" in result.output


def test_a_case_without_a_card_prints_nothing_more(theatre: str) -> None:
    invoke(
        theatre,
        "schedule",
        "add-case",
        "OR4-01",
        "--room",
        "OR4",
        "--surgeon",
        "Bell",
        "--procedure",
        "cystoscopy",
        "--start",
        "2025-04-17 09:00",
        "--minutes",
        "45",
    )
    result = invoke(theatre, "schedule", "case", "OR4-01")
    assert "none" in result.output
    assert "essential" not in result.output


def test_an_unknown_case_exits_not_found(theatre: str) -> None:
    assert invoke(theatre, "schedule", "case", "OR9-99").exit_code == 3


LIST_FILE = """case,room,surgeon,procedure,start,minutes,card
OR5-01,OR5,Bell,cystoscopy,2025-04-17 09:00,45,
OR5-02,OR5,Bell,ureteroscopy,2025-04-17 10:00,60,PC-118
"""


def test_a_theatre_export_is_imported(theatre: str, tmp_path: Path) -> None:
    path = tmp_path / "list.csv"
    path.write_text(LIST_FILE, encoding="utf-8")
    result = invoke(theatre, "schedule", "import", str(path))
    assert result.exit_code == 0
    assert "2 cases read" in result.output
    assert "rooms: OR5" in result.output
    listed = invoke(theatre, "schedule", "day", "--on", "2025-04-17")
    assert "OR5-01" in listed.output


def test_a_dry_run_saves_nothing(theatre: str, tmp_path: Path) -> None:
    path = tmp_path / "list.csv"
    path.write_text(LIST_FILE, encoding="utf-8")
    result = invoke(theatre, "schedule", "import", str(path), "--dry-run")
    assert "dry run, nothing was saved" in result.output
    listed = invoke(theatre, "schedule", "day", "--on", "2025-04-17")
    assert "OR5-01" not in listed.output


def test_a_bad_row_is_reported_and_exits_two(theatre: str, tmp_path: Path) -> None:
    path = tmp_path / "list.csv"
    path.write_text(LIST_FILE + "OR6-01,OR6\n", encoding="utf-8")
    result = invoke(theatre, "schedule", "import", str(path))
    assert result.exit_code == 2
    assert "wrong number of fields" in result.output
