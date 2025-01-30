from __future__ import annotations

import pytest

from tests.cli.conftest import invoke

CASE = "OR3-20250128-01"


@pytest.fixture
def floor(db: str) -> str:
    invoke(db, "tray", "register", "ORT-0114", "ORT-MAJOR")
    invoke(db, "tray", "register", "ORT-0115", "ORT-MAJOR")
    for asset in ("ORT-0114", "ORT-0115"):
        for stage in ("decontamination", "clean", "assembled", "sterilizing", "cooling", "sterile"):
            invoke(db, "tray", "move", asset, stage)
    return db


def test_issuing_a_tray_records_it_and_moves_it(floor: str) -> None:
    result = invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    assert result.exit_code == 0
    assert "out to OR3-20250128-01" in result.output
    shown = invoke(floor, "tray", "show", "ORT-0114", "--no-history")
    assert "issued" in shown.output


def test_two_trays_can_go_to_one_case(floor: str) -> None:
    result = invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114", "--tray", "ORT-0115")
    assert result.output.count("out to") == 2


def test_a_tray_already_out_cannot_be_issued_again(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    result = invoke(floor, "case", "issue", "OR4-20250128-02", "--tray", "ORT-0114")
    assert result.exit_code == 4


def test_an_unknown_tray_exits_not_found(floor: str) -> None:
    result = invoke(floor, "case", "issue", CASE, "--tray", "XX-1")
    assert result.exit_code == 3


def test_an_unopened_tray_goes_back_on_the_shelf(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    result = invoke(floor, "case", "return", "ORT-0114", "--as", "unopened")
    assert result.exit_code == 0
    assert "back from OR3-20250128-01 unopened" in result.output
    shown = invoke(floor, "tray", "show", "ORT-0114", "--no-history")
    assert "sterile" in shown.output


def test_an_opened_tray_goes_to_the_washer(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    invoke(floor, "case", "return", "ORT-0114", "--as", "opened")
    shown = invoke(floor, "tray", "show", "ORT-0114", "--no-history")
    assert "soiled" in shown.output


def test_a_used_tray_passes_through_in_use(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    invoke(floor, "case", "return", "ORT-0114", "--as", "used")
    shown = invoke(floor, "tray", "show", "ORT-0114")
    assert "in use" in shown.output
    assert "soiled" in shown.output


def test_returning_a_tray_that_is_not_out_is_refused(floor: str) -> None:
    result = invoke(floor, "case", "return", "ORT-0114", "--as", "used")
    assert result.exit_code != 0
    assert "not out to a case" in result.output


def test_a_case_lists_its_trays(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114", "--tray", "ORT-0115")
    invoke(floor, "case", "return", "ORT-0114", "--as", "used")
    result = invoke(floor, "case", "show", CASE)
    assert "ORT-0114" in result.output
    assert "used" in result.output
    assert "open" in result.output


def test_the_out_list_shows_what_is_in_theatre(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    result = invoke(floor, "case", "out")
    assert "ORT-0114" in result.output
    assert CASE in result.output


def test_where_answers_as_a_recall_would(floor: str) -> None:
    invoke(floor, "case", "issue", CASE, "--tray", "ORT-0114")
    result = invoke(floor, "case", "where", "ORT-0114")
    assert "issued OR3-20250128-01" in result.output
    assert "retrieve from the room" in result.output
    unknown = invoke(floor, "case", "where", "XX-1")
    assert "unknown" in unknown.output
