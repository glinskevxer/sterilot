from __future__ import annotations

from click.testing import Result

from tests.cli.conftest import invoke


def raise_one(db: str, reference: str = "NC-1", *extra: str) -> Result:
    return invoke(
        db,
        "quality",
        "raise",
        reference,
        "wet pack on unloading",
        "--category",
        "sterilization",
        "--subject",
        "AC-1",
        *extra,
    )


def test_raising_an_exception_reports_the_due_date(db: str) -> None:
    result = raise_one(db)
    assert result.exit_code == 0
    assert "NC-1 minor sterilization on AC-1, open" in result.output
    assert "response due" in result.output


def test_an_unknown_category_is_a_validation_failure(db: str) -> None:
    result = invoke(db, "quality", "raise", "NC-1", "x", "--category", "vibes")
    assert result.exit_code == 2


def test_an_exception_reads_back_in_full(db: str) -> None:
    raise_one(db, "NC-1", "--action", "load reprocessed")
    result = invoke(db, "quality", "show", "NC-1")
    assert result.exit_code == 0
    assert "wet pack on unloading" in result.output
    assert "immediate action: load reprocessed" in result.output


def test_an_unknown_reference_exits_not_found(db: str) -> None:
    result = invoke(db, "quality", "show", "NC-9")
    assert result.exit_code == 3


def test_open_exceptions_are_listed_with_their_due_dates(db: str) -> None:
    raise_one(db, "NC-1")
    raise_one(db, "NC-2", "--severity", "critical")
    result = invoke(db, "quality", "open")
    assert "NC-1" in result.output
    assert "critical" in result.output


def test_a_minor_finding_closes_without_an_investigation(db: str) -> None:
    raise_one(db)
    result = invoke(db, "quality", "close", "NC-1")
    assert result.exit_code == 0
    assert "closed" in result.output
    assert invoke(db, "quality", "open").output.count("NC-1") == 0


def test_a_major_finding_will_not_close_without_one(db: str) -> None:
    raise_one(db, "NC-1", "--severity", "major")
    bare = invoke(db, "quality", "close", "NC-1")
    assert bare.exit_code == 2
    done = invoke(db, "quality", "close", "NC-1", "--investigation", "steam trap replaced")
    assert done.exit_code == 0


def test_a_critical_finding_cannot_close_the_same_day(db: str) -> None:
    raise_one(db, "NC-1", "--severity", "critical")
    result = invoke(db, "quality", "close", "NC-1", "--investigation", "load recalled")
    assert result.exit_code == 2
    assert "does not close the day it opened" in result.output


def test_trends_count_by_category_and_name_repeats(db: str) -> None:
    for index in range(3):
        raise_one(db, f"NC-{index}")
    invoke(
        db,
        "quality",
        "raise",
        "NC-9",
        "tray short",
        "--category",
        "assembly",
        "--subject",
        "ORT-0114",
    )
    result = invoke(db, "quality", "trends", "--from", "2000-01-01", "--to", "2100-01-01")
    assert "sterilization" in result.output
    assert "AC-1: 3 exceptions" in result.output


def test_the_audit_trail_reads_back_and_says_the_chain_holds(db: str) -> None:
    raise_one(db)
    invoke(db, "quality", "close", "NC-1")
    result = invoke(db, "quality", "audit")
    assert "recorded" in result.output
    assert "closed" in result.output
    assert "chain intact" in result.output


def test_the_audit_trail_can_be_filtered(db: str) -> None:
    raise_one(db, "NC-1")
    raise_one(db, "NC-2")
    result = invoke(db, "quality", "audit", "--kind", "exception", "--subject", "NC-1")
    assert "NC-1" in result.output
    assert "NC-2" not in result.output
