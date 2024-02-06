from __future__ import annotations

from datetime import date

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import (
    LotControlNumber,
    asset_tag,
    badge_number,
    case_number,
    catalog_number,
    equipment_id,
    indicator_lot,
    normalise_code,
    tray_code,
)


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("su-1234", "SU-1234"),
        ("  su 1234 ", "SU-1234"),
        ("su_1234", "SU-1234"),
        ("su/1234", "SU-1234"),
        ("su.1234", "SU-1234"),
        ("su---1234", "SU-1234"),
        ("-su-1234-", "SU-1234"),
        ("ORT MAJOR SET", "ORT-MAJOR-SET"),
    ],
)
def test_normalise_collapses_every_separator(raw: str, clean: str) -> None:
    assert normalise_code(raw, field="code") == clean


def test_normalise_refuses_empty() -> None:
    with pytest.raises(ValidationError):
        normalise_code("   ", field="code")


def test_normalise_refuses_punctuation_only() -> None:
    with pytest.raises(ValidationError):
        normalise_code("---", field="code")


def test_normalise_refuses_characters_the_printer_cannot_render() -> None:
    with pytest.raises(ValidationError) as caught:
        normalise_code("su#1234", field="catalog number")
    assert "catalog number" in caught.value.message


def test_normalise_refuses_a_code_over_the_label_width() -> None:
    with pytest.raises(ValidationError) as caught:
        normalise_code("A" * 40, field="code", max_length=32)
    assert caught.value.context["max_length"] == 32


def test_normalise_refuses_a_non_string() -> None:
    with pytest.raises(ValidationError):
        normalise_code(1234, field="code")  # type: ignore[arg-type]


def test_each_field_has_its_own_width() -> None:
    assert catalog_number("su 1234") == "SU-1234"
    assert asset_tag("ort 0114") == "ORT-0114"
    assert tray_code("ort major") == "ORT-MAJOR"
    assert badge_number("t 4471") == "T-4471"
    assert case_number("or3 2024 0115 07") == "OR3-2024-0115-07"
    assert indicator_lot("bi 24a17") == "BI-24A17"
    assert equipment_id("ac 1") == "AC-1"


def test_badge_width_is_short() -> None:
    with pytest.raises(ValidationError):
        badge_number("T-44710000000000")


def test_lot_control_number_formats() -> None:
    lcn = LotControlNumber("AC1", date(2024, 1, 15), 3)
    assert lcn.format() == "AC1-20240115-03"
    assert str(lcn) == "AC1-20240115-03"


def test_lot_control_number_normalises_its_sterilizer() -> None:
    assert LotControlNumber("ac 1", date(2024, 1, 15), 3).sterilizer == "AC-1"


def test_lot_control_number_round_trips() -> None:
    lcn = LotControlNumber("AC1", date(2025, 9, 30), 12)
    assert LotControlNumber.parse(lcn.format()) == lcn


def test_lot_control_number_parses_lower_case_with_spaces() -> None:
    assert LotControlNumber.parse(" ac1-20240115-3 ") == LotControlNumber(
        "AC1", date(2024, 1, 15), 3
    )


@pytest.mark.parametrize(
    "text",
    ["", "AC1", "AC1-2024011-03", "AC1-20240115", "AC1-20240115-", "AC1/20240115/03"],
)
def test_lot_control_number_refuses_the_wrong_shape(text: str) -> None:
    with pytest.raises(ValidationError):
        LotControlNumber.parse(text)


def test_lot_control_number_refuses_an_impossible_date() -> None:
    with pytest.raises(ValidationError):
        LotControlNumber.parse("AC1-20240230-01")


def test_run_number_has_bounds() -> None:
    with pytest.raises(ValidationError):
        LotControlNumber("AC1", date(2024, 1, 15), 0)
    with pytest.raises(ValidationError):
        LotControlNumber("AC1", date(2024, 1, 15), 100)


def test_lot_control_numbers_sort_by_sterilizer_then_date_then_run() -> None:
    first = LotControlNumber("AC1", date(2024, 1, 15), 1)
    second = LotControlNumber("AC1", date(2024, 1, 15), 2)
    third = LotControlNumber("AC2", date(2024, 1, 14), 1)
    assert sorted([third, second, first]) == [first, second, third]
