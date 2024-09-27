from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.quality.nonconformance import (
    Category,
    ExceptionRegister,
    Nonconformance,
    Severity,
)

RAISED = datetime(2024, 10, 1, 9, 0)


def entry(**changes: object) -> Nonconformance:
    values: dict[str, object] = {
        "reference": "nc 4401",
        "category": Category.STERILIZATION,
        "severity": Severity.MINOR,
        "raised_at": RAISED,
        "raised_by": "t 4471",
        "description": "wet pack found on unloading",
        "subject": "AC-1",
    }
    values.update(changes)
    return Nonconformance(**values)  # type: ignore[arg-type]


def test_severity_response_times_and_investigation() -> None:
    assert Severity.named("critical") is Severity.CRITICAL
    assert Severity.CRITICAL.response_days == 1
    assert Severity.OBSERVATION.response_days == 30
    assert Severity.MAJOR.needs_investigation
    assert not Severity.MINOR.needs_investigation
    with pytest.raises(ValidationError):
        Severity.named("annoying")


def test_category_lookup() -> None:
    assert Category.named("point of use") is Category.POINT_OF_USE
    assert Category.LOANER.label == "loaner"
    with pytest.raises(ValidationError):
        Category.named("other")


def test_an_exception_says_what_happened() -> None:
    with pytest.raises(ValidationError):
        entry(description="   ")


def test_identifiers_are_normalised() -> None:
    made = entry()
    assert made.reference == "NC-4401"
    assert made.raised_by == "T-4471"
    assert made.open


def test_the_due_date_follows_the_severity() -> None:
    assert entry().due_on() == date(2024, 10, 15)
    assert entry(severity=Severity.CRITICAL).due_on() == date(2024, 10, 2)


def test_overdue_only_applies_while_open() -> None:
    made = entry()
    assert not made.overdue(date(2024, 10, 10))
    assert made.overdue(date(2024, 10, 20))
    closed = made.closed(datetime(2024, 10, 3, 9, 0), "T-9002")
    assert not closed.overdue(date(2024, 10, 20))


def test_age_stops_at_the_closing_date() -> None:
    made = entry().closed(datetime(2024, 10, 4, 9, 0), "T-9002")
    assert made.age_days(date(2024, 11, 1)) == 3
    assert entry().age_days(date(2024, 10, 11)) == 10


def test_closing_needs_a_signature() -> None:
    with pytest.raises(ValidationError):
        entry(closed_at=datetime(2024, 10, 3, 9, 0))


def test_a_close_cannot_predate_the_raise() -> None:
    with pytest.raises(ValidationError):
        entry(closed_at=datetime(2024, 9, 1, 9, 0), closed_by="T-9002")


def test_a_major_finding_closes_with_an_investigation() -> None:
    with pytest.raises(ValidationError):
        entry(severity=Severity.MAJOR, closed_at=datetime(2024, 10, 3, 9, 0), closed_by="T-9002")
    closed = entry(severity=Severity.MAJOR).closed(
        datetime(2024, 10, 3, 9, 0), "T-9002", "steam supply retested"
    )
    assert closed.investigation == "steam supply retested"


def test_a_critical_finding_does_not_close_the_same_day() -> None:
    with pytest.raises(ValidationError):
        entry(severity=Severity.CRITICAL).closed(
            datetime(2024, 10, 1, 16, 0), "T-9002", "load recalled"
        )
    closed = entry(severity=Severity.CRITICAL).closed(
        datetime(2024, 10, 2, 9, 0), "T-9002", "load recalled"
    )
    assert not closed.open


def test_closing_twice_is_refused() -> None:
    closed = entry().closed(datetime(2024, 10, 3, 9, 0), "T-9002")
    with pytest.raises(ConflictError):
        closed.closed(datetime(2024, 10, 4, 9, 0), "T-9002")


def test_summary_reads_like_the_register_line() -> None:
    assert entry().summary() == "NC-4401 minor sterilization on AC-1, open"
    assert entry(subject="").summary() == "NC-4401 minor sterilization, open"


def test_the_register_refuses_a_duplicate_reference() -> None:
    register = ExceptionRegister.of([entry()])
    with pytest.raises(ConflictError):
        register.with_entry(entry())


def test_the_register_finds_and_replaces() -> None:
    register = ExceptionRegister.of([entry(), entry(reference="NC-4402")])
    closed = register.get("nc 4401").closed(datetime(2024, 10, 3, 9, 0), "T-9002")
    register = register.replacing(closed)
    assert not register.get("NC-4401").open
    assert len(register.open_entries()) == 1
    with pytest.raises(NotFoundError):
        register.get("NC-9999")
    with pytest.raises(NotFoundError):
        ExceptionRegister().replacing(entry())


def test_the_register_lists_what_is_overdue() -> None:
    register = ExceptionRegister.of(
        [entry(), entry(reference="NC-4402", severity=Severity.OBSERVATION)]
    )
    assert [item.reference for item in register.overdue(date(2024, 10, 20))] == ["NC-4401"]


def test_counts_by_category() -> None:
    register = ExceptionRegister.of(
        [
            entry(),
            entry(reference="NC-4402"),
            entry(reference="NC-4403", category=Category.CLEANING),
        ]
    )
    assert register.by_category() == {Category.STERILIZATION: 2, Category.CLEANING: 1}


def test_entries_about_one_subject() -> None:
    register = ExceptionRegister.of([entry(), entry(reference="NC-4402", subject="AC-2")])
    assert [item.reference for item in register.about("ac-1")] == ["NC-4401"]


def test_repeat_subjects_surface_the_real_problem() -> None:
    register = ExceptionRegister.of(
        [
            entry(reference="NC-1"),
            entry(reference="NC-2"),
            entry(reference="NC-3"),
            entry(reference="NC-4", subject="AC-2"),
        ]
    )
    assert register.repeat_subjects() == (("AC-1", 3),)
    assert register.repeat_subjects(threshold=2) == (("AC-1", 3),)


def test_repeat_subjects_needs_a_real_threshold() -> None:
    with pytest.raises(ValidationError):
        ExceptionRegister().repeat_subjects(threshold=1)
