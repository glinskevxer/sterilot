from __future__ import annotations

import pytest

from tests.cli.conftest import invoke


@pytest.fixture
def bench(db: str) -> str:
    for number in ("SU-1234", "SU-1235", "SU-9001"):
        invoke(
            db,
            "catalog",
            "add",
            number,
            "forceps",
            "--manufacturer",
            "V Mueller",
            "--complexity",
            "hinged",
            "--grams",
            "60",
        )
    invoke(
        db,
        "sheet",
        "define",
        "ORT-MAJOR",
        "orthopaedic major set",
        "--line",
        "SU-1234=4",
        "--line",
        "SU-1235=2",
        "--from",
        "2025-01-01",
    )
    return db


def test_a_complete_tray_counts_clean(bench: str) -> None:
    result = invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=4",
        "--item",
        "SU-1235=2",
        "--on",
        "2025-04-01",
    )
    assert result.exit_code == 0
    assert "counts complete" in result.output


def test_a_short_tray_exits_with_the_policy_status(bench: str) -> None:
    result = invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=3",
        "--item",
        "SU-1235=2",
        "--on",
        "2025-04-01",
    )
    assert result.exit_code == 5
    assert "SU-1234 short 1 of 4" in result.output


def test_a_foreign_instrument_is_named(bench: str) -> None:
    result = invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=4",
        "--item",
        "SU-1235=2",
        "--item",
        "SU-9001=1",
        "--on",
        "2025-04-01",
    )
    assert result.exit_code == 0
    assert "SU-9001 is not on this sheet" in result.output


def test_an_approved_replacement_covers_the_gap(bench: str) -> None:
    invoke(bench, "sheet", "substitute", "SU-1234", "SU-9001", "--from", "2025-01-01")
    result = invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=3",
        "--item",
        "SU-9001=1",
        "--item",
        "SU-1235=2",
        "--on",
        "2025-04-01",
    )
    assert result.exit_code == 0
    assert "1 x SU-9001 covering 1 x SU-1234" in result.output


def test_an_unapproved_replacement_does_not(bench: str) -> None:
    result = invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=3",
        "--item",
        "SU-9001=1",
        "--item",
        "SU-1235=2",
        "--on",
        "2025-04-01",
    )
    assert result.exit_code == 5


def test_a_short_tray_can_raise_its_own_exception(bench: str) -> None:
    result = invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=3",
        "--item",
        "SU-1235=2",
        "--on",
        "2025-04-01",
        "--asset",
        "ORT-0114",
        "--raise-exception",
        "NC-77",
    )
    assert result.exit_code == 5
    assert "raised NC-77" in result.output
    shown = invoke(bench, "quality", "show", "NC-77")
    assert "ORT-0114" in shown.output
    assert "SU-1234 short 1 of 4" in shown.output


def test_a_complete_tray_raises_nothing(bench: str) -> None:
    invoke(
        bench,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=4",
        "--item",
        "SU-1235=2",
        "--on",
        "2025-04-01",
        "--raise-exception",
        "NC-78",
    )
    assert invoke(bench, "quality", "show", "NC-78").exit_code == 3


def test_the_sheet_view_shows_what_to_count(bench: str) -> None:
    result = invoke(bench, "count", "sheet", "ORT-MAJOR", "--on", "2025-04-01")
    assert result.exit_code == 0
    assert "pieces" in result.output
    assert "SU-1234" in result.output
    assert "known weight" in result.output


def test_an_unknown_set_exits_not_found(bench: str) -> None:
    assert invoke(bench, "count", "sheet", "NOPE").exit_code == 3
