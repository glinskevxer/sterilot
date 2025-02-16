from __future__ import annotations

import pytest

from tests.cli.conftest import invoke


@pytest.fixture
def people(db: str) -> str:
    invoke(db, "staff", "add", "T-4471", "R Ferreira")
    invoke(db, "staff", "add", "T-9002", "M Iqbal", "--role", "supervisor")
    invoke(db, "staff", "add", "T-9100", "A Novak", "--role", "trainee")
    return db


def test_adding_somebody_reports_their_role(db: str) -> None:
    result = invoke(db, "staff", "add", "t 4471", "R Ferreira")
    assert result.exit_code == 0
    assert "added T-4471 R Ferreira as technician" in result.output


def test_an_unknown_role_is_a_validation_failure(db: str) -> None:
    result = invoke(db, "staff", "add", "T-1", "A Person", "--role", "boss")
    assert result.exit_code == 2


def test_a_certification_is_recorded(people: str) -> None:
    result = invoke(
        people,
        "staff",
        "certify",
        "T-4471",
        "--body",
        "HSPA",
        "--number",
        "CRCST-1",
        "--from",
        "2023-01-01",
        "--to",
        "2026-01-01",
    )
    assert result.exit_code == 0
    assert "T-4471 holds 1 certifications" in result.output


def test_a_certification_for_an_unknown_badge_exits_not_found(db: str) -> None:
    result = invoke(
        db,
        "staff",
        "certify",
        "T-4471",
        "--body",
        "HSPA",
        "--number",
        "CRCST-1",
        "--from",
        "2023-01-01",
    )
    assert result.exit_code == 3


def test_a_competency_is_recorded(people: str) -> None:
    result = invoke(people, "staff", "assess", "T-9100", "assembly", "--on", "2025-02-01")
    assert result.exit_code == 0
    assert "T-9100 assembly assessed 2025-02-01" in result.output


def test_nobody_assesses_themselves(people: str) -> None:
    result = invoke(people, "staff", "assess", "T-4471", "assembly")
    assert result.exit_code == 2
    assert "nobody assesses themselves" in result.output


def test_a_high_risk_task_needs_three_observations(people: str) -> None:
    single = invoke(people, "staff", "assess", "T-9100", "release")
    assert single.exit_code == 2
    triple = invoke(people, "staff", "assess", "T-9100", "release", "--observations", "3")
    assert triple.exit_code == 0


def test_show_prints_the_person_and_their_records(people: str) -> None:
    invoke(
        people,
        "staff",
        "certify",
        "T-9002",
        "--body",
        "HSPA",
        "--number",
        "CRCST-1",
        "--from",
        "2023-01-01",
        "--to",
        "2030-01-01",
    )
    invoke(people, "staff", "assess", "T-9002", "assembly", "--on", "2026-08-01")
    result = invoke(people, "staff", "show", "T-9002")
    assert "M Iqbal" in result.output
    assert "HSPA CRCST-1" in result.output
    assert "assembly" in result.output
    assert "may release" in result.output


def test_the_roster_says_who_may_sign_a_release(people: str) -> None:
    invoke(
        people,
        "staff",
        "certify",
        "T-4471",
        "--body",
        "HSPA",
        "--number",
        "CRCST-1",
        "--from",
        "2023-01-01",
        "--to",
        "2030-01-01",
    )
    invoke(people, "staff", "assess", "T-4471", "release", "--observations", "3", badge="T-9002")
    result = invoke(people, "staff", "roster")
    lines = [line for line in result.output.splitlines() if "T-" in line]
    assert any(line.startswith("T-4471") and line.endswith("yes") for line in lines)
    assert any("does not sign a release" in line for line in lines)


def test_an_uncertified_technician_cannot_release(people: str) -> None:
    result = invoke(people, "staff", "roster")
    assert "certification is not current" in result.output


def test_competencies_about_to_lapse_are_listed(people: str) -> None:
    invoke(people, "staff", "assess", "T-9100", "assembly", "--on", "2025-10-01")
    result = invoke(people, "staff", "due", "--within", "3650")
    assert "T-9100" in result.output
    assert "assembly" in result.output
