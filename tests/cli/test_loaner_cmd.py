from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.cli.conftest import invoke

CASE_START = datetime.now() + timedelta(days=3)
CASE_DAY = CASE_START.strftime("%Y-%m-%d")


@pytest.fixture
def booked(db: str) -> str:
    invoke(
        db,
        "loaner",
        "book",
        "LN-44",
        "--vendor",
        "Medline Ortho",
        "--set-name",
        "revision knee tray 2",
        "--case",
        "OR3-01",
        "--case-start",
        CASE_START.strftime("%Y-%m-%d %H:%M"),
        "--expected",
        (CASE_START - timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
    )
    return db


def test_booking_reports_the_deadline(db: str) -> None:
    result = invoke(
        db,
        "loaner",
        "book",
        "LN-44",
        "--vendor",
        "Medline",
        "--set-name",
        "knee tray",
        "--case",
        "OR3-01",
        "--case-start",
        CASE_START.strftime("%Y-%m-%d %H:%M"),
        "--expected",
        (CASE_START - timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
    )
    assert result.exit_code == 0
    assert "booked LN-44 knee tray for OR3-01" in result.output
    assert "due by" in result.output


def test_a_loaner_expected_after_the_case_is_refused(db: str) -> None:
    result = invoke(
        db,
        "loaner",
        "book",
        "LN-44",
        "--vendor",
        "Medline",
        "--set-name",
        "knee tray",
        "--case",
        "OR3-01",
        "--case-start",
        CASE_START.strftime("%Y-%m-%d %H:%M"),
        "--expected",
        (CASE_START + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
    )
    assert result.exit_code == 2


def test_receiving_reports_the_lead_time(booked: str) -> None:
    result = invoke(booked, "loaner", "receive", "LN-44")
    assert result.exit_code == 0
    assert "received" in result.output
    assert "hours before the case" in result.output


def test_counting_before_arrival_is_refused(booked: str) -> None:
    result = invoke(booked, "loaner", "count", "LN-44", "--pieces", "214")
    assert result.exit_code != 0
    assert "has not arrived" in result.output


def test_a_full_intake_makes_the_set_ready(booked: str) -> None:
    invoke(booked, "loaner", "receive", "LN-44")
    invoke(booked, "loaner", "count", "LN-44", "--pieces", "214")
    result = invoke(booked, "loaner", "reprocessed", "LN-44")
    assert result.exit_code == 0
    assert "reprocessed" in result.output
    shown = invoke(booked, "loaner", "show", "LN-44")
    assert "ready" in shown.output
    assert "yes" in shown.output


def test_a_count_without_the_rep_is_reported(booked: str) -> None:
    invoke(booked, "loaner", "receive", "LN-44")
    invoke(booked, "loaner", "count", "LN-44", "--pieces", "214", "--no-rep")
    result = invoke(booked, "loaner", "reprocessed", "LN-44")
    assert "without the vendor representative" in result.output


def test_show_lists_what_is_still_missing(booked: str) -> None:
    result = invoke(booked, "loaner", "show", "LN-44")
    assert "expected" in result.output
    assert "the set has not arrived" in result.output


def test_the_due_list_names_the_ones_that_are_not_ready(booked: str) -> None:
    result = invoke(booked, "loaner", "due", "--on", CASE_DAY)
    assert result.exit_code == 0
    assert "LN-44" in result.output
    assert "not arrived" in result.output


def test_a_ready_day_says_so(booked: str) -> None:
    invoke(booked, "loaner", "receive", "LN-44")
    invoke(booked, "loaner", "count", "LN-44", "--pieces", "214")
    invoke(booked, "loaner", "reprocessed", "LN-44")
    result = invoke(booked, "loaner", "due", "--on", CASE_DAY)
    assert "every loaner for that day is ready" in result.output


def test_outstanding_lists_what_is_in_the_building(booked: str) -> None:
    result = invoke(booked, "loaner", "outstanding")
    assert "LN-44" in result.output
    assert "Medline Ortho" in result.output


def test_an_unknown_reference_exits_not_found(db: str) -> None:
    assert invoke(db, "loaner", "show", "LN-99").exit_code == 3
