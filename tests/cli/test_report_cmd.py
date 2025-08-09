from __future__ import annotations

import pytest

from tests.cli.conftest import add_sterilizer, assemble, invoke, record_cycle


@pytest.fixture
def busy(db: str) -> str:
    add_sterilizer(db)
    assemble(db, "ORT-0114")
    invoke(db, "duty", "log", "AC-1", "air removal", "--on", "2025-02-14")
    invoke(db, "duty", "log", "AC-1", "biological", "--on", "2025-02-14")
    record_cycle(db, "2025-02-14 08:00", run=1)
    invoke(db, "load", "build", "LD-1", "--lot", "AC-1-20250214-01", "--tray", "ORT-0114")
    invoke(
        db,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "ORT-0114",
        "--internal",
        "ORT-0114",
    )
    return db


def test_the_daily_report_prints_the_day(busy: str) -> None:
    result = invoke(busy, "report", "daily", "--on", "2025-02-14")
    assert result.exit_code == 0
    assert "Central Service daily report 2025-02-14" in result.output
    assert "AC-1-20250214-01" in result.output
    assert "LD-1" in result.output
    assert "verdict" in result.output


def test_a_quiet_day_reports_nothing_to_report(busy: str) -> None:
    result = invoke(busy, "report", "daily", "--on", "2025-02-15")
    assert "nothing to report" in result.output


def test_a_missing_daily_test_shows_up(db: str) -> None:
    add_sterilizer(db)
    record_cycle(db, "2025-02-14 08:00", run=1)
    result = invoke(db, "report", "daily", "--on", "2025-02-14")
    assert "AC-1 has no air removal test" in result.output
    assert "see below" in result.output


def test_throughput_counts_by_day(busy: str) -> None:
    result = invoke(busy, "report", "throughput", "--from", "2025-02-01", "--to", "2025-03-01")
    assert result.exit_code == 0
    assert "2025-02-14" in result.output
    assert "per load" in result.output


def test_quality_reports_yield_and_rework(busy: str) -> None:
    result = invoke(busy, "report", "quality", "--from", "2025-02-01", "--to", "2025-03-01")
    assert result.exit_code == 0
    assert "first pass yield" in result.output
    assert "100.0 percent" in result.output


def test_quality_says_when_there_is_nothing_to_measure(db: str) -> None:
    result = invoke(db, "report", "quality", "--from", "2025-02-01", "--to", "2025-03-01")
    assert result.exit_code == 0
    assert "no loads in that window" in result.output


def test_a_held_load_is_listed_in_the_quality_report(busy: str) -> None:
    assemble(busy, "IMP-0001", "IMP-KNEE")
    record_cycle(busy, "2025-02-14 10:00", run=2)
    invoke(
        busy,
        "load",
        "build",
        "LD-2",
        "--lot",
        "AC-1-20250214-02",
        "--tray",
        "IMP-0001",
        "--implant",
        "IMP-0001",
    )
    invoke(
        busy,
        "load",
        "release",
        "LD-2",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
    )
    result = invoke(busy, "report", "quality", "--from", "2025-02-01", "--to", "2025-03-01")
    assert "LD-2" in result.output
    assert "implant" in result.output
    assert "50.0 percent" in result.output


def test_the_machine_report_shows_what_ran_and_what_was_tested(busy: str) -> None:
    result = invoke(busy, "report", "machines", "--on", "2025-02-14")
    assert result.exit_code == 0
    assert "AC-1" in result.output
    assert "air removal" in result.output
    assert "ready" in result.output


def test_a_machine_with_nothing_logged_says_none(db: str) -> None:
    add_sterilizer(db)
    result = invoke(db, "report", "machines", "--on", "2025-02-14")
    assert "none" in result.output


def test_turnaround_says_when_there_is_nothing(db: str) -> None:
    result = invoke(db, "report", "turnaround", "--from", "2025-02-01", "--to", "2025-03-01")
    assert result.exit_code == 0
    assert "no completed turnarounds" in result.output


def test_turnaround_reports_the_tail(busy: str) -> None:
    result = invoke(busy, "report", "turnaround", "--from", "2020-01-01", "--to", "2030-01-01")
    assert result.exit_code == 0
    assert "Turnaround in hours" in result.output
    assert "ninetieth" in result.output
    assert "ORT-0114" in result.output
