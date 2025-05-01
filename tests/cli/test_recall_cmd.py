from __future__ import annotations

import pytest

from sterilot.store.store import Store
from tests.cli.conftest import add_sterilizer, assemble, invoke, record_cycle


@pytest.fixture
def recalled(db: str) -> str:
    add_sterilizer(db)
    invoke(db, "duty", "log", "AC-1", "biological", "--on", "2025-01-19")
    for index, asset in enumerate(("ORT-0114", "ORT-0115", "ORT-0116"), start=1):
        assemble(db, asset)
        record_cycle(db, f"2025-01-20 {7 + index:02d}:00", run=index)
        invoke(
            db,
            "load",
            "build",
            f"LD-{index}",
            "--lot",
            f"AC-1-20250120-0{index}",
            "--tray",
            asset,
        )
    return db


def test_the_scope_names_every_load_since_the_last_pass(recalled: str) -> None:
    result = invoke(recalled, "recall", "scope", "--equipment", "AC-1", "--at", "2025-01-20 18:00")
    assert result.exit_code == 0
    assert "3 loads back to the last passing test" in result.output
    assert "LD-1" in result.output
    assert "LD-3" in result.output


def test_the_scope_stops_at_a_passing_test(recalled: str) -> None:
    invoke(recalled, "duty", "log", "AC-1", "biological", "--on", "2025-01-21")
    record_cycle(recalled, "2025-01-20 12:00", run=4)
    assemble(recalled, "ORT-0117")
    invoke(recalled, "load", "build", "LD-4", "--lot", "AC-1-20250120-04", "--tray", "ORT-0117")
    result = invoke(recalled, "recall", "scope", "--equipment", "AC-1", "--at", "2025-01-22 09:00")
    assert "0 loads" in result.output


def test_the_tray_list_says_what_to_do_with_each_one(recalled: str) -> None:
    result = invoke(recalled, "recall", "trays", "--equipment", "AC-1", "--at", "2025-01-20 18:00")
    assert result.exit_code == 0
    assert "ORT-0114" in result.output
    assert "locate the tray" in result.output


def test_raising_a_recall_marks_the_loads(recalled: str) -> None:
    result = invoke(
        recalled, "recall", "raise", "RC-2025-01", "--equipment", "AC-1", "--at", "2025-01-20 18:00"
    )
    assert result.exit_code == 0
    assert "recall RC-2025-01 raised" in result.output
    assert "marked 3 loads recalled" in result.output
    shown = invoke(recalled, "load", "show", "LD-1")
    assert "recalled" in shown.output


def test_a_dry_run_changes_nothing(recalled: str) -> None:
    result = invoke(
        recalled,
        "recall",
        "raise",
        "RC-2025-01",
        "--equipment",
        "AC-1",
        "--at",
        "2025-01-20 18:00",
        "--dry-run",
    )
    assert "dry run, nothing was marked" in result.output
    shown = invoke(recalled, "load", "show", "LD-1")
    assert "pending" in shown.output


def test_raising_a_recall_writes_an_audit_entry(recalled: str) -> None:
    invoke(
        recalled, "recall", "raise", "RC-2025-01", "--equipment", "AC-1", "--at", "2025-01-20 18:00"
    )
    with Store.open(recalled) as store:
        events = store.quality.audit_for("recall", "RC-2025-01")
        assert len(events) == 1
        assert events[0].detail == "3 loads on AC-1"
        assert store.quality.audit_trail().intact()


def test_an_air_removal_recall_uses_its_own_history(recalled: str) -> None:
    result = invoke(
        recalled,
        "recall",
        "scope",
        "--equipment",
        "AC-1",
        "--kind",
        "bowie dick",
        "--at",
        "2025-01-20 18:00",
    )
    assert result.exit_code == 0
    assert "air removal failure" in result.output
    assert "back to the first record" in result.output


def test_an_unknown_kind_is_a_validation_failure(recalled: str) -> None:
    result = invoke(
        recalled,
        "recall",
        "scope",
        "--equipment",
        "AC-1",
        "--kind",
        "guess",
        "--at",
        "2025-01-20 18:00",
    )
    assert result.exit_code == 2
