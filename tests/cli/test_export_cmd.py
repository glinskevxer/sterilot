from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import invoke, working_day


@pytest.fixture
def busy(db: str) -> str:
    working_day(db, "2025-06-03", "2025-06-03 08:00")
    invoke(
        db,
        "quality",
        "raise",
        "NC-1",
        "wet pack",
        "--category",
        "sterilization",
        "--subject",
        "AC-1",
    )
    return db


def test_cycles_export_to_standard_output(busy: str) -> None:
    result = invoke(busy, "export", "cycles", "--from", "2025-06-01", "--to", "2025-07-01")
    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("lot,sterilizer")
    assert "AC-1-20250603-01" in result.output


def test_one_chamber_can_be_asked_for(busy: str) -> None:
    result = invoke(
        busy,
        "export",
        "cycles",
        "--from",
        "2025-06-01",
        "--to",
        "2025-07-01",
        "--equipment",
        "AC-2",
    )
    assert result.exit_code == 0
    assert len(result.output.splitlines()) == 1


def test_loads_export_with_their_status(busy: str) -> None:
    result = invoke(busy, "export", "loads", "--from", "2025-06-01", "--to", "2025-07-01")
    assert "LD-1" in result.output
    assert "released" in result.output


def test_exceptions_export(busy: str) -> None:
    result = invoke(busy, "export", "exceptions", "--from", "2025-01-01", "--to", "2030-01-01")
    assert "NC-1" in result.output
    assert "wet pack" in result.output


def test_an_export_can_go_to_a_file(busy: str, tmp_path: Path) -> None:
    target = tmp_path / "cycles.csv"
    result = invoke(
        busy,
        "export",
        "cycles",
        "--from",
        "2025-06-01",
        "--to",
        "2025-07-01",
        "--to-file",
        str(target),
    )
    assert result.exit_code == 0
    assert "wrote 1 rows" in result.output
    assert "AC-1-20250603-01" in target.read_text(encoding="utf-8")


def test_a_tab_delimiter_can_be_asked_for(busy: str) -> None:
    result = invoke(
        busy,
        "export",
        "loads",
        "--from",
        "2025-06-01",
        "--to",
        "2025-07-01",
        "--delimiter",
        "\t",
    )
    assert "\t" in result.output.splitlines()[0]


def test_an_empty_window_exports_only_the_header(busy: str) -> None:
    result = invoke(busy, "export", "loads", "--from", "2024-01-01", "--to", "2024-02-01")
    assert len(result.output.splitlines()) == 1
