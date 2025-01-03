from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main


@pytest.fixture
def db(tmp_path: Path) -> str:
    return str(tmp_path / "sterilot.sqlite3")


def run(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, "--badge", "T-4471", *args])


def add_sterilizer(db: str, equipment: str = "AC-1", *extra: str) -> Result:
    return run(
        db,
        "machine",
        "add-sterilizer",
        equipment,
        "--model",
        "Amsco 400",
        "--manufacturer",
        "Steris",
        "--method",
        "prevac",
        *extra,
    )


def add_washer(db: str, equipment: str = "WD-2", *extra: str) -> Result:
    return run(
        db,
        "machine",
        "add-washer",
        equipment,
        "--model",
        "Reliance 444",
        "--manufacturer",
        "Steris",
        "--qualified",
        "2024-01-10",
        *extra,
    )


def test_a_sterilizer_registers(db: str) -> None:
    result = add_sterilizer(db)
    assert result.exit_code == 0
    assert "registered AC-1 Amsco 400" in result.output


def test_a_sterilizer_with_no_method_is_refused(db: str) -> None:
    result = run(db, "machine", "add-sterilizer", "AC-1", "--model", "x", "--manufacturer", "y")
    assert result.exit_code == 2


def test_a_chamber_mixing_steam_and_low_temperature_is_refused(db: str) -> None:
    result = add_sterilizer(db, "AC-1", "--method", "peroxide")
    assert result.exit_code == 2
    assert "no chamber runs both" in result.output


def test_a_washer_registers(db: str) -> None:
    result = add_washer(db)
    assert result.exit_code == 0
    assert "registered WD-2" in result.output


def test_the_list_says_what_can_run(db: str) -> None:
    add_sterilizer(db)
    add_washer(db)
    result = run(db, "machine", "list")
    assert result.exit_code == 0
    assert "AC-1" in result.output
    assert "sterilizer" in result.output
    assert "ready" in result.output


def test_a_washer_past_qualification_says_so_in_the_list(db: str) -> None:
    add_washer(db, "WD-3", "--qualified", "2019-01-01")
    result = run(db, "machine", "list")
    assert "past its qualification date" in result.output


def test_duties_come_from_the_machine(db: str) -> None:
    add_sterilizer(db)
    add_washer(db)
    steam = run(db, "machine", "duties", "AC-1")
    assert "air removal" in steam.output
    assert "biological" in steam.output
    washer = run(db, "machine", "duties", "WD-2")
    assert washer.output.strip() == "cleaning"


def test_an_ultrasonic_owes_nothing_daily(db: str) -> None:
    add_washer(db, "US-1", "--class", "ultrasonic")
    result = run(db, "machine", "duties", "US-1")
    assert result.output.strip() == "nothing daily"


def test_show_prints_a_sterilizer(db: str) -> None:
    add_sterilizer(db, "AC-1", "--chamber", "double")
    result = run(db, "machine", "show", "AC-1")
    assert "capacity" in result.output
    assert "12" in result.output
    assert "ready" in result.output


def test_show_prints_a_washer(db: str) -> None:
    add_washer(db)
    result = run(db, "machine", "show", "WD-2")
    assert "single chamber" in result.output
    assert "disinfects" in result.output


def test_a_repair_puts_the_chamber_in_the_queue(db: str) -> None:
    add_sterilizer(db)
    result = run(db, "machine", "repaired", "AC-1")
    assert "owes 3 qualification runs" in result.output
    listed = run(db, "machine", "list")
    assert "owes 3 qualification runs" in listed.output


def test_an_unknown_machine_exits_not_found(db: str) -> None:
    result = run(db, "machine", "show", "AC-9")
    assert result.exit_code == 3
