from __future__ import annotations

import pytest

from tests.cli.conftest import add_sterilizer, invoke


@pytest.fixture
def planned(db: str) -> str:
    add_sterilizer(db)
    invoke(
        db,
        "maintenance",
        "add",
        "AC-1",
        "PM-1",
        "door gasket",
        "--every-days",
        "180",
        "--last-done",
        "2025-01-01",
    )
    invoke(db, "maintenance", "add", "AC-1", "PM-2", "chamber drain", "--every-cycles", "100")
    return db


def test_a_task_goes_on_the_schedule(db: str) -> None:
    result = invoke(db, "maintenance", "add", "AC-1", "pm 1", "door gasket", "--every-days", "180")
    assert result.exit_code == 0
    assert "PM-1 door gasket every 180 days" in result.output


def test_a_task_with_no_interval_is_refused(db: str) -> None:
    result = invoke(db, "maintenance", "add", "AC-1", "PM-1", "door gasket")
    assert result.exit_code == 2


def test_the_schedule_lists_a_machine(planned: str) -> None:
    result = invoke(planned, "maintenance", "list", "AC-1")
    assert "PM-1" in result.output
    assert "PM-2" in result.output


def test_a_task_never_done_is_due(planned: str) -> None:
    result = invoke(planned, "maintenance", "due", "--on", "2025-06-28")
    assert "PM-2" in result.output
    assert "never done" in result.output
    assert "PM-1" not in result.output


def test_looking_ahead_finds_the_calendar_task(planned: str) -> None:
    result = invoke(planned, "maintenance", "due", "--on", "2025-06-28", "--within", "30")
    assert "2025-06-30" in result.output


def test_doing_a_task_moves_it_on(planned: str) -> None:
    result = invoke(planned, "maintenance", "done", "AC-1", "PM-2", "--on", "2025-06-28")
    assert result.exit_code == 0
    assert "PM-2 done 2025-06-28" in result.output
    after = invoke(planned, "maintenance", "due", "--on", "2025-06-28")
    assert "PM-2" not in after.output


def test_a_calendar_task_reports_its_next_date(planned: str) -> None:
    result = invoke(planned, "maintenance", "done", "AC-1", "PM-1", "--on", "2025-06-28")
    assert "next 2025-12-25" in result.output


def test_a_cycle_counts_against_the_cycle_driven_jobs(planned: str) -> None:
    invoke(planned, "maintenance", "done", "AC-1", "PM-2", "--on", "2025-06-28")
    result = invoke(planned, "maintenance", "ran", "AC-1")
    assert "PM-2: 99 cycles left" in result.output
    assert "PM-1" not in result.output


def test_a_machine_with_no_cycle_jobs_says_so(db: str) -> None:
    add_sterilizer(db)
    invoke(db, "maintenance", "add", "AC-1", "PM-1", "gasket", "--every-days", "180")
    result = invoke(db, "maintenance", "ran", "AC-1")
    assert "no cycle driven jobs" in result.output


def test_an_unknown_task_exits_not_found(planned: str) -> None:
    assert invoke(planned, "maintenance", "done", "AC-1", "PM-9").exit_code == 3
