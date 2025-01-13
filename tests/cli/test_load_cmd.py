from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main


def run(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, "--badge", "T-4471", *args])


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
    run(path, "tray", "register", "ORT-0114", "ORT-MAJOR")
    run(path, "tray", "register", "IMP-0001", "IMP-KNEE")
    run(
        path,
        "cycle",
        "record",
        "--equipment",
        "AC-1",
        "--method",
        "prevac",
        "--started",
        "2025-01-14 08:00",
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
    )
    run(path, "duty", "log", "AC-1", "air removal", "--on", "2025-01-14")
    return path


LOT = "AC-1-20250114-01"


def build(db: str, *extra: str) -> Result:
    return run(db, "load", "build", "LD-1", "--lot", LOT, "--tray", "ORT-0114", *extra)


def release(db: str, *extra: str) -> Result:
    return run(
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
        *extra,
    )


def test_a_load_builds_against_a_recorded_cycle(db: str) -> None:
    result = build(db)
    assert result.exit_code == 0
    assert "built LD-1 (1 items) on AC-1-20250114-01" in result.output


def test_building_against_an_unknown_lot_exits_not_found(db: str) -> None:
    result = run(db, "load", "build", "LD-9", "--lot", "AC-1-20250114-09", "--tray", "ORT-0114")
    assert result.exit_code == 3


def test_building_with_an_unknown_tray_exits_not_found(db: str) -> None:
    result = run(db, "load", "build", "LD-9", "--lot", LOT, "--tray", "XX-1")
    assert result.exit_code == 3


def test_a_clean_load_releases(db: str) -> None:
    build(db)
    result = release(db)
    assert result.exit_code == 0
    assert "released routine" in result.output


def test_a_load_with_no_internal_indicator_is_rejected(db: str) -> None:
    build(db)
    result = run(
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
    )
    assert result.exit_code == 5
    assert "no internal indicator" in result.output


def test_a_failed_strip_is_named_against_its_tray(db: str) -> None:
    build(db)
    result = release(db, "--internal", "ORT-0114=fail")
    assert result.exit_code == 5
    assert "the internal indicator failed" in result.output


def test_a_wet_load_is_rejected(db: str) -> None:
    build(db)
    result = release(db, "--wet")
    assert result.exit_code == 5
    assert "came out wet" in result.output


def test_a_missing_air_removal_test_rejects_the_load(tmp_path: Path) -> None:
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
    run(path, "tray", "register", "ORT-0114", "ORT-MAJOR")
    run(
        path,
        "cycle",
        "record",
        "--equipment",
        "AC-1",
        "--method",
        "prevac",
        "--started",
        "2025-01-14 08:00",
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
    )
    build(path)
    result = release(path)
    assert result.exit_code == 5
    assert "no passing air removal test" in result.output


def test_an_implant_load_is_held_until_the_biological_is_read(db: str) -> None:
    run(db, "load", "build", "LD-1", "--lot", LOT, "--tray", "IMP-0001", "--implant", "IMP-0001")
    result = run(
        db,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
    )
    assert result.exit_code == 5
    assert "carries an implant" in result.output


def test_an_implant_load_releases_once_the_biological_reads(db: str) -> None:
    run(db, "load", "build", "LD-1", "--lot", LOT, "--tray", "IMP-0001", "--implant", "IMP-0001")
    result = run(
        db,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
        "--biological",
        "pass",
    )
    assert result.exit_code == 0
    assert "released implant" in result.output


def test_a_failed_biological_rejects_the_load(db: str) -> None:
    build(db)
    result = release(db, "--biological", "fail")
    assert result.exit_code == 5
    assert "the biological indicator grew" in result.output


def test_show_prints_the_load_and_its_reasons(db: str) -> None:
    build(db)
    release(db, "--wet")
    result = run(db, "load", "show", "LD-1")
    assert result.exit_code == 0
    assert "rejected" in result.output
    assert "came out wet" in result.output
    assert "ORT-0114" in result.output


def test_held_loads_are_listed(db: str) -> None:
    run(db, "load", "build", "LD-1", "--lot", LOT, "--tray", "IMP-0001", "--implant", "IMP-0001")
    run(
        db,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
    )
    result = run(db, "load", "held")
    assert "LD-1" in result.output
    assert "implant" in result.output


def test_loads_of_a_tray_are_listed(db: str) -> None:
    build(db)
    result = run(db, "load", "of-tray", "ort 0114")
    assert "LD-1" in result.output
    assert "pending" in result.output
