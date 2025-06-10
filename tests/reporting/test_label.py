from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.methods import Method
from sterilot.reporting.label import LABEL_WIDTH, Label, for_package, sheet
from sterilot.settings import Settings
from sterilot.storage.event import Package, Packaging

LOT = LotControlNumber("AC-1", date(2025, 6, 9), 3)
STERILIZED = datetime(2025, 6, 9, 8, 40)


def label(**changes: object) -> Label:
    values: dict[str, object] = {
        "asset": "ort 0114",
        "code": "ort major",
        "lot": LOT,
        "method": Method.STEAM_PREVAC,
        "sterilized_at": STERILIZED,
        "assembled_by": "t 4471",
    }
    values.update(changes)
    return Label(**values)  # type: ignore[arg-type]


def test_identifiers_are_normalised() -> None:
    made = label()
    assert made.asset == "ORT-0114"
    assert made.code == "ORT-MAJOR"
    assert made.assembled_by == "T-4471"


def test_an_expiry_before_the_cycle_is_refused() -> None:
    with pytest.raises(ValidationError):
        label(expires_on=date(2025, 6, 1))


def test_an_event_related_label_says_so() -> None:
    assert label().expiry_line == "sterile unless opened or damaged"


def test_a_dated_label_prints_the_date() -> None:
    assert label(expires_on=date(2025, 12, 6)).expiry_line == "use by 2025-12-06"


def test_the_label_carries_the_lot_control_number() -> None:
    lines = label().lines()
    assert "AC-1-20250609-03" in lines
    assert "ORT-MAJOR  ORT-0114" in lines
    assert "assembled by T-4471" in lines


def test_a_facility_line_is_printed_when_there_is_one() -> None:
    assert label(facility="Ridgeway CS").lines()[0] == "Ridgeway CS"
    assert label().lines()[0] == "ORT-MAJOR  ORT-0114"


def test_the_rendered_label_fits_the_printer() -> None:
    rendered = label(facility="Ridgeway Central Service Department").render()
    assert all(len(line) <= LABEL_WIDTH for line in rendered.splitlines())
    assert rendered.splitlines()[0] == "-" * LABEL_WIDTH


def test_a_label_is_built_from_a_package() -> None:
    package = Package("ORT-0114", LOT, Packaging.SEQUENTIAL_WRAP, STERILIZED)
    made = for_package(package, "ORT-MAJOR", Method.STEAM_PREVAC, "T-4471")
    assert made.expires_on is None
    assert made.facility == "Central Service"


def test_a_shelf_life_setting_puts_a_date_on_the_label() -> None:
    package = Package("ORT-0114", LOT, Packaging.SEQUENTIAL_WRAP, STERILIZED)
    made = for_package(
        package, "ORT-MAJOR", Method.STEAM_PREVAC, "T-4471", Settings(shelf_life_days=180)
    )
    assert made.expires_on == date(2025, 12, 6)
    assert "use by" in made.render()


def test_a_sheet_stacks_labels_by_default() -> None:
    rendered = sheet((label(), label()))
    assert rendered.count("AC-1-20250609-03") == 2


def test_a_sheet_can_print_them_side_by_side() -> None:
    rendered = sheet((label(), label()), across=2)
    first = rendered.splitlines()[1]
    assert first.count("ORT-0114") == 2


def test_an_odd_label_on_a_wide_sheet_still_prints() -> None:
    rendered = sheet((label(), label(), label()), across=2)
    assert rendered.count("ORT-0114") == 3


def test_a_sheet_needs_at_least_one_across() -> None:
    with pytest.raises(ValidationError):
        sheet((label(),), across=0)
