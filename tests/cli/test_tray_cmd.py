from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main


@pytest.fixture
def db(tmp_path: Path) -> str:
    return str(tmp_path / "sterilot.sqlite3")


def run(db: str, *args: str, badge: str = "T-4471") -> Result:
    return CliRunner().invoke(main, ["--db", db, "--badge", badge, *args])


def unsigned(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, *args])


def register(db: str, asset: str = "ORT-0114") -> Result:
    return run(db, "tray", "register", asset, "ort major")


def test_registering_a_tray_reports_it(db: str) -> None:
    result = register(db)
    assert result.exit_code == 0
    assert "registered ORT-0114 (ORT-MAJOR)" in result.output


def test_registering_without_a_badge_is_refused(db: str) -> None:
    result = unsigned(db, "tray", "register", "ORT-0114", "ORT-MAJOR")
    assert result.exit_code == 7
    assert "needs a badge" in result.output


def test_a_loaner_needs_an_owner(db: str) -> None:
    result = run(db, "tray", "register", "LN-1", "REV-KNEE", "--ownership", "loaner")
    assert result.exit_code == 2
    assert "name its owner" in result.output


def test_a_loaner_with_an_owner_registers(db: str) -> None:
    result = run(
        db, "tray", "register", "LN-1", "REV-KNEE", "--ownership", "loaner", "--owner", "Medline"
    )
    assert result.exit_code == 0


def test_moving_a_tray_follows_the_transition_table(db: str) -> None:
    register(db)
    good = run(db, "tray", "move", "ORT-0114", "decontamination")
    assert good.exit_code == 0
    assert "is now decontamination" in good.output
    bad = run(db, "tray", "move", "ORT-0114", "sterile")
    assert bad.exit_code == 4
    assert "not a move a tray can make" in bad.output


def test_moving_an_unknown_tray_exits_not_found(db: str) -> None:
    result = run(db, "tray", "move", "XX-1", "decontamination")
    assert result.exit_code == 3


def test_an_unknown_stage_is_a_validation_failure(db: str) -> None:
    register(db)
    result = run(db, "tray", "move", "ORT-0114", "somewhere")
    assert result.exit_code == 2


def test_show_prints_the_tray_and_its_history(db: str) -> None:
    register(db)
    run(db, "tray", "move", "ORT-0114", "decontamination", "--note", "heavy soil")
    result = run(db, "tray", "show", "ORT-0114")
    assert result.exit_code == 0
    assert "ORT-MAJOR" in result.output
    assert "heavy soil" in result.output
    assert "placed in service" in result.output


def test_show_can_leave_the_history_out(db: str) -> None:
    register(db)
    result = run(db, "tray", "show", "ORT-0114", "--no-history")
    assert "placed in service" not in result.output


def test_next_lists_the_legal_moves(db: str) -> None:
    register(db)
    result = run(db, "tray", "next", "ORT-0114")
    assert result.exit_code == 0
    assert "decontamination" in result.output
    assert "sterile" not in result.output


def test_the_board_counts_by_stage(db: str) -> None:
    register(db, "ORT-0114")
    register(db, "ORT-0115")
    run(db, "tray", "move", "ORT-0115", "decontamination")
    result = run(db, "tray", "board")
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert any(line.startswith("soiled") and line.endswith("1") for line in lines)
    assert any(line.startswith("decontamination") for line in lines)


def test_trays_of_a_set_are_listed(db: str) -> None:
    register(db, "ORT-0114")
    register(db, "ORT-0115")
    result = run(db, "tray", "of-set", "ort major")
    assert "ORT-0114" in result.output
    assert "ORT-0115" in result.output
