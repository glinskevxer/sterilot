from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import click
import pytest
from click.testing import CliRunner, Result

from sterilot import __version__
from sterilot.cli.context import BADGE_ENV, DB_ENV, Context, default_badge, default_db_path
from sterilot.cli.main import main
from sterilot.clock import Clock
from sterilot.errors import ConfigurationError, NotFoundError, ValidationError
from sterilot.store.db import Database
from sterilot.store.migrations import latest_version


def run(args: list[str], tmp_path: Path) -> Result:
    runner = CliRunner()
    return runner.invoke(main, ["--db", str(tmp_path / "sterilot.sqlite3"), *args])


def test_the_version_prints() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_the_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "status" in result.output
    assert "health" in result.output


def test_status_opens_and_migrates_the_database(tmp_path: Path) -> None:
    result = run(["status"], tmp_path)
    assert result.exit_code == 0
    assert "Central Service" in result.output
    assert str(latest_version()) in result.output
    assert (tmp_path / "sterilot.sqlite3").exists()


def test_status_reports_the_badge_when_one_is_given(tmp_path: Path) -> None:
    result = run(["status"], tmp_path)
    assert "not set" in result.output
    runner = CliRunner()
    signed = runner.invoke(
        main, ["--db", str(tmp_path / "sterilot.sqlite3"), "--badge", "t 4471", "status"]
    )
    assert "T-4471" in signed.output


def test_health_says_nothing_is_wrong(tmp_path: Path) -> None:
    result = run(["health"], tmp_path)
    assert result.exit_code == 0
    assert "no problems found" in result.output


def test_health_exits_non_zero_when_something_is_wrong(tmp_path: Path) -> None:
    runner = CliRunner()
    path = tmp_path / "sterilot.sqlite3"
    runner.invoke(main, ["--db", str(path), "status"])
    db = Database.open(path)
    db.execute(
        "INSERT INTO audit_event (at, by_badge, action, subject_kind, subject, previous)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ["2024-12-12T09:00:00", "T-4471", "recorded", "load", "LD-1", "nonsense"],
    )
    db.close()
    result = runner.invoke(main, ["--db", str(path), "health"])
    assert result.exit_code == 6
    assert "audit trail" in result.output


def test_a_settings_file_is_read(tmp_path: Path) -> None:
    settings = tmp_path / "sterilot.toml"
    settings.write_text("[sterilot]\nfacility = 'Ridgeway CS'\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--db",
            str(tmp_path / "sterilot.sqlite3"),
            "--settings",
            str(settings),
            "status",
        ],
    )
    assert "Ridgeway CS" in result.output


def test_a_missing_settings_file_is_refused(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--db",
            str(tmp_path / "sterilot.sqlite3"),
            "--settings",
            str(tmp_path / "nope.toml"),
            "status",
        ],
    )
    assert result.exit_code != 0


def test_where_prints_the_default_path() -> None:
    result = CliRunner().invoke(main, ["where"])
    assert result.exit_code == 0
    assert result.output.strip() == str(default_db_path())


def test_the_default_path_follows_the_environment() -> None:
    os.environ[DB_ENV] = "/tmp/elsewhere.sqlite3"
    try:
        assert str(default_db_path()) == "/tmp/elsewhere.sqlite3"
    finally:
        del os.environ[DB_ENV]


def test_the_default_badge_follows_the_environment() -> None:
    assert default_badge() is None
    os.environ[BADGE_ENV] = "T-4471"
    try:
        assert default_badge() == "T-4471"
    finally:
        del os.environ[BADGE_ENV]


def test_a_context_without_a_badge_refuses_to_sign(tmp_path: Path) -> None:
    context = Context.build(tmp_path / "sterilot.sqlite3")
    try:
        assert context.badge is None
        try:
            context.signed_by()
        except ConfigurationError as error:
            assert "badge" in error.message
        else:  # pragma: no cover
            raise AssertionError("expected a refusal")
    finally:
        context.close()


def test_a_context_with_a_badge_signs(tmp_path: Path) -> None:
    context = Context.build(tmp_path / "sterilot.sqlite3", badge="t 4471")
    try:
        assert context.signed_by() == "T-4471"
        assert context.now() is not None
    finally:
        context.close()


def test_the_doctor_says_when_nothing_is_outstanding(tmp_path: Path) -> None:
    result = run(["doctor"], tmp_path)
    assert result.exit_code == 0
    assert "nothing outstanding" in result.output


def test_the_doctor_exits_with_the_policy_status_on_a_stop(tmp_path: Path) -> None:
    path = str(tmp_path / "sterilot.sqlite3")
    runner = CliRunner()
    runner.invoke(
        main,
        [
            "--db",
            path,
            "--badge",
            "T-4471",
            "machine",
            "add-sterilizer",
            "AC-1",
            "--model",
            "Amsco",
            "--manufacturer",
            "Steris",
            "--method",
            "prevac",
        ],
    )
    runner.invoke(main, ["--db", path, "--badge", "T-4471", "machine", "repaired", "AC-1"])
    result = runner.invoke(main, ["--db", path, "doctor"])
    assert result.exit_code == 5
    assert "owes 3 qualification runs" in result.output


def test_the_board_prints_the_quiet_department(tmp_path: Path) -> None:
    result = run(["board"], tmp_path)
    assert result.exit_code == 0
    assert "trays in the loop" in result.output
    assert "Central Service board" in result.output


def test_the_board_counts_a_tray_in_the_loop(tmp_path: Path) -> None:
    path = str(tmp_path / "sterilot.sqlite3")
    runner = CliRunner()
    runner.invoke(
        main, ["--db", path, "--badge", "T-4471", "tray", "register", "ORT-0114", "ORT-MAJOR"]
    )
    result = runner.invoke(main, ["--db", path, "board"])
    assert "soiled" in result.output


def test_the_command_list_names_every_group() -> None:
    result = CliRunner().invoke(main, ["commands"])
    assert result.exit_code == 0
    names = [line.split()[0] for line in result.output.splitlines() if line.strip()]
    for expected in ("catalog", "cycle", "load", "recall", "report", "shelf", "staff"):
        assert expected in names


def test_each_command_carries_a_summary() -> None:
    result = CliRunner().invoke(main, ["commands"])
    for line in result.output.splitlines():
        assert len(line.split()) > 1, line


def test_the_help_explains_the_exit_statuses() -> None:
    result = CliRunner().invoke(main, ["--help"])
    flat = " ".join(result.output.split())
    assert "Exit statuses: 0 fine" in flat
    assert "5 a rule refused it" in flat
    assert "STERILOT_DB" in flat


def test_every_group_has_help_text() -> None:
    from sterilot.cli.main import main as root

    for name, command in root.commands.items():
        assert command.help, name


def test_every_subcommand_carries_help_text() -> None:
    from sterilot.cli.main import main as root

    missing: list[str] = []
    for name, command in root.commands.items():
        if not isinstance(command, click.Group):
            continue
        for child, found in command.commands.items():
            if not found.help:
                missing.append(f"{name} {child}")
    assert missing == []


def test_the_command_list_is_sorted() -> None:
    result = CliRunner().invoke(main, ["commands"])
    names = [line.split()[0] for line in result.output.splitlines() if line.strip()]
    assert names == sorted(names)


def test_the_context_day_falls_back_to_the_processing_day(tmp_path: Path) -> None:
    context = Context.build(
        tmp_path / "sterilot.sqlite3", clock=Clock(fixed=datetime(2025, 8, 12, 2, 0))
    )
    try:
        assert context.day() == date(2025, 8, 11)
        assert context.day("2025-08-20") == date(2025, 8, 20)
    finally:
        context.close()


def test_the_context_day_refuses_nonsense(tmp_path: Path) -> None:
    context = Context.build(tmp_path / "sterilot.sqlite3")
    try:
        with pytest.raises(ValidationError):
            context.day("last tuesday")
    finally:
        context.close()


def test_an_error_prints_its_context_and_what_a_script_will_see(tmp_path: Path) -> None:
    result = run(["catalog", "show", "SU-9999"], tmp_path)
    assert result.exit_code == 3
    lines = result.output.strip().splitlines()
    assert lines[0] == "sterilot: we do not stock that catalog number"
    assert lines[1].strip() == "catalog: SU-9999"
    assert lines[-1].strip() == "(exit 3, not found)"


def test_an_error_with_no_context_still_names_the_status(tmp_path: Path) -> None:
    result = run(["catalog", "sheet", "NOPE"], tmp_path)
    assert result.exit_code == 3
    assert "(exit 3, not found)" in result.output


def test_debug_lets_the_error_out_with_its_traceback(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--db", str(tmp_path / "sterilot.sqlite3"), "--debug", "catalog", "show", "SU-9999"],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, NotFoundError)
