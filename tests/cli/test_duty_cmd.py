from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main
from sterilot.quality.log import Duty
from sterilot.store.store import Store


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "sterilot.sqlite3")
    run(
        path,
        "machine",
        "add-sterilizer",
        "AC-1",
        "--model",
        "Amsco",
        "--manufacturer",
        "Steris",
        "--method",
        "prevac",
    )
    run(
        path,
        "machine",
        "add-washer",
        "WD-2",
        "--model",
        "Reliance",
        "--manufacturer",
        "Steris",
        "--qualified",
        "2025-01-02",
    )
    return path


def run(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, "--badge", "T-4471", *args])


def test_logging_a_pass_reports_it(db: str) -> None:
    result = run(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-10")
    assert result.exit_code == 0
    assert "AC-1 air removal pass" in result.output


def test_logging_a_failure_needs_a_note(db: str) -> None:
    bare = run(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-10", "--failed")
    assert bare.exit_code == 2
    noted = run(
        db,
        "duty",
        "log",
        "AC-1",
        "air removal",
        "--on",
        "2025-01-10",
        "--failed",
        "--note",
        "uneven colour",
    )
    assert noted.exit_code == 0
    assert "FAIL, uneven colour" in noted.output


def test_the_day_view_says_what_is_still_owed(db: str) -> None:
    run(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-10")
    result = run(db, "duty", "day", "AC-1", "--on", "2025-01-10")
    assert result.exit_code == 0
    assert "air removal" in result.output
    assert "still owed: biological" in result.output


def test_a_covered_day_owes_nothing(db: str) -> None:
    run(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-10")
    run(db, "duty", "log", "AC-1", "biological", "--on", "2025-01-10")
    result = run(db, "duty", "day", "AC-1", "--on", "2025-01-10")
    assert "still owed" not in result.output


def test_a_washer_owes_only_cleaning(db: str) -> None:
    result = run(db, "duty", "day", "WD-2", "--on", "2025-01-10")
    assert "still owed: cleaning" in result.output


def test_failures_are_listed_for_a_window(db: str) -> None:
    run(
        db,
        "duty",
        "log",
        "AC-1",
        "air removal",
        "--on",
        "2025-01-10",
        "--failed",
        "--note",
        "uneven colour",
    )
    run(db, "duty", "log", "AC-1", "biological", "--on", "2025-01-11")
    result = run(db, "duty", "failures", "--from", "2025-01-01", "--to", "2025-02-01")
    assert "2025-01-10" in result.output
    assert "uneven colour" in result.output
    assert "biological" not in result.output


def test_the_store_answers_whether_air_removal_passed(db: str) -> None:
    run(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-10")
    with Store.open(db) as store:
        assert store.duties.air_removal_ok("AC-1", date(2025, 1, 10))
        assert not store.duties.air_removal_ok("AC-1", date(2025, 1, 11))
        assert store.duties.covered("AC-1", date(2025, 1, 10), frozenset({Duty.AIR_REMOVAL}))
        entry = store.duties.get("AC-1", date(2025, 1, 10), Duty.AIR_REMOVAL)
        assert entry.passed


def test_a_failed_air_removal_does_not_count_as_cover(db: str) -> None:
    run(
        db,
        "duty",
        "log",
        "AC-1",
        "air removal",
        "--on",
        "2025-01-10",
        "--failed",
        "--note",
        "uneven",
    )
    with Store.open(db) as store:
        assert not store.duties.air_removal_ok("AC-1", date(2025, 1, 10))


def test_a_window_of_entries_reads_back_as_a_log(db: str) -> None:
    run(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-10")
    run(db, "duty", "log", "WD-2", "cleaning", "--on", "2025-01-10")
    with Store.open(db) as store:
        log = store.duties.between(date(2025, 1, 1), date(2025, 2, 1))
        assert len(log.entries) == 2
        assert log.covered("WD-2", date(2025, 1, 10), frozenset({Duty.CLEANING}))
