from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main


@pytest.fixture
def db(tmp_path: Path) -> str:
    return str(tmp_path / "sterilot.sqlite3")


def run(db: str, *args: str) -> Result:
    return CliRunner().invoke(main, ["--db", db, *args])


def add_forceps(db: str) -> Result:
    return run(
        db,
        "catalog",
        "add",
        "su 1234",
        "kelly forceps",
        "--manufacturer",
        "V Mueller",
        "--complexity",
        "hinged",
        "--grams",
        "60",
    )


def test_adding_an_instrument_reports_what_was_saved(db: str) -> None:
    result = add_forceps(db)
    assert result.exit_code == 0
    assert "saved SU-1234 kelly forceps" in result.output


def test_an_instrument_comes_back_with_its_methods(db: str) -> None:
    add_forceps(db)
    result = run(db, "catalog", "show", "su 1234")
    assert result.exit_code == 0
    assert "V Mueller" in result.output
    assert "surgical stainless steel" in result.output
    assert "steam, dynamic air removal" in result.output


def test_an_instrument_that_cannot_take_a_method_says_why(db: str) -> None:
    run(
        db,
        "catalog",
        "add",
        "PL-1",
        "polymer retractor",
        "--manufacturer",
        "Aesculap",
        "--material",
        "PL",
    )
    result = run(db, "catalog", "show", "PL-1")
    assert "methods it does not" in result.output
    assert "rated to 60.0 C" in result.output


def test_an_unstocked_number_exits_with_the_not_found_status(db: str) -> None:
    result = run(db, "catalog", "show", "SU-9999")
    assert result.exit_code == 3
    assert "we do not stock" in result.output


def test_a_bad_material_is_a_validation_failure(db: str) -> None:
    result = run(
        db, "catalog", "add", "SU-1", "probe", "--manufacturer", "Pilling", "--material", "XX"
    )
    assert result.exit_code == 2


def test_a_lumened_item_needs_its_channel_measured(db: str) -> None:
    result = run(
        db,
        "catalog",
        "add",
        "SU-9001",
        "suction",
        "--manufacturer",
        "Pilling",
        "--complexity",
        "lumened",
    )
    assert result.exit_code == 2
    assert "needs its channel measured" in result.output


def test_the_instrument_list_is_a_table(db: str) -> None:
    add_forceps(db)
    result = run(db, "catalog", "list")
    assert "catalog" in result.output
    assert "SU-1234" in result.output


def test_the_material_list_needs_no_database(db: str) -> None:
    result = run(db, "catalog", "materials")
    assert result.exit_code == 0
    assert "anodised aluminium" in result.output
    assert "hydrogen_peroxide" in result.output


def test_sets_are_empty_until_one_is_defined(db: str) -> None:
    result = run(db, "catalog", "sets")
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_a_sheet_can_be_read_back_for_a_day(db: str) -> None:
    add_forceps(db)
    from datetime import date

    from sterilot.catalog.revision import RevisionHistory
    from sterilot.catalog.tray import CountLine, CountSheet
    from sterilot.store.store import Store

    with Store.open(db) as store:
        item = store.catalog.instrument("SU-1234")
        sheet = CountSheet.of("ORT-MAJOR", "ortho major", [CountLine(item, quantity=6)])
        store.catalog.save_history(RevisionHistory.started(sheet, date(2024, 1, 1)))
    result = run(db, "catalog", "sheet", "ort major", "--on", "2024-06-01")
    assert result.exit_code == 0
    assert "ORT-MAJOR rev 1" in result.output
    assert "kelly forceps" in result.output
    assert "steam_prevac" in result.output


def test_an_unknown_set_exits_not_found(db: str) -> None:
    result = run(db, "catalog", "sheet", "NOPE")
    assert result.exit_code == 3
