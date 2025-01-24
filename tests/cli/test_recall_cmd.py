from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main


def run(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, "--badge", "T-4471", *args])


def record_cycle(db: str, run_number: int, hour: int) -> None:
    run(
        db,
        "cycle",
        "record",
        "--equipment",
        "AC-1",
        "--method",
        "prevac",
        "--started",
        f"2025-01-20 {hour:02d}:00",
        "--temp",
        "133.4C",
        "--exposure",
        "4",
        "--dry",
        "31",
        "--pulses",
        "4",
        "--pressure",
        "29.6 psig",
        "--run",
        str(run_number),
    )


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
    run(path, "duty", "log", "AC-1", "biological", "--on", "2025-01-19")
    for index, asset in enumerate(("ORT-0114", "ORT-0115", "ORT-0116"), start=1):
        run(path, "tray", "register", asset, "ORT-MAJOR")
        record_cycle(path, index, 7 + index)
        run(
            path,
            "load",
            "build",
            f"LD-{index}",
            "--lot",
            f"AC-1-20250120-0{index}",
            "--tray",
            asset,
        )
    return path


def test_the_scope_names_every_load_since_the_last_pass(db: str) -> None:
    result = run(db, "recall", "scope", "--equipment", "AC-1", "--at", "2025-01-20 18:00")
    assert result.exit_code == 0
    assert "3 loads back to the last passing test" in result.output
    assert "LD-1" in result.output
    assert "LD-3" in result.output


def test_the_scope_stops_at_a_passing_test(db: str) -> None:
    run(db, "duty", "log", "AC-1", "biological", "--on", "2025-01-21")
    record_cycle(db, 4, 12)
    run(db, "tray", "register", "ORT-0117", "ORT-MAJOR")
    run(db, "load", "build", "LD-4", "--lot", "AC-1-20250120-04", "--tray", "ORT-0117")
    result = run(db, "recall", "scope", "--equipment", "AC-1", "--at", "2025-01-22 09:00")
    assert "0 loads" in result.output


def test_the_tray_list_says_what_to_do_with_each_one(db: str) -> None:
    result = run(db, "recall", "trays", "--equipment", "AC-1", "--at", "2025-01-20 18:00")
    assert result.exit_code == 0
    assert "ORT-0114" in result.output
    assert "locate the tray" in result.output


def test_raising_a_recall_marks_the_loads(db: str) -> None:
    result = run(
        db, "recall", "raise", "RC-2025-01", "--equipment", "AC-1", "--at", "2025-01-20 18:00"
    )
    assert result.exit_code == 0
    assert "recall RC-2025-01 raised" in result.output
    assert "marked 3 loads recalled" in result.output
    shown = run(db, "load", "show", "LD-1")
    assert "recalled" in shown.output


def test_a_dry_run_changes_nothing(db: str) -> None:
    result = run(
        db,
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
    shown = run(db, "load", "show", "LD-1")
    assert "pending" in shown.output


def test_raising_a_recall_writes_an_audit_entry(db: str) -> None:
    run(db, "recall", "raise", "RC-2025-01", "--equipment", "AC-1", "--at", "2025-01-20 18:00")
    from sterilot.store.store import Store

    with Store.open(db) as store:
        events = store.quality.audit_for("recall", "RC-2025-01")
        assert len(events) == 1
        assert events[0].detail == "3 loads on AC-1"
        assert store.quality.audit_trail().intact()


def test_an_air_removal_recall_uses_its_own_history(db: str) -> None:
    result = run(
        db,
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


def test_an_unknown_kind_is_a_validation_failure(db: str) -> None:
    result = run(
        db, "recall", "scope", "--equipment", "AC-1", "--kind", "guess", "--at", "2025-01-20 18:00"
    )
    assert result.exit_code == 2
