from __future__ import annotations

from datetime import date

import pytest

from sterilot.catalog.count import count_tray
from sterilot.catalog.instrument import Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.substitution import Substitution, SubstitutionTable
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import ValidationError
from sterilot.interval import DateRange

DAY = date(2024, 5, 1)


def item(catalog: str) -> Instrument:
    return Instrument(catalog, "forceps", "V Mueller", material_named("SS"))


def sheet() -> CountSheet:
    return CountSheet.of(
        "ORT-MAJOR",
        "orthopaedic major set",
        [
            CountLine(item("SU-1"), quantity=4),
            CountLine(item("SU-2"), quantity=2),
            CountLine(item("SU-3"), quantity=1, required=False),
        ],
    )


def table(ratio: int = 1) -> SubstitutionTable:
    return SubstitutionTable.of(
        [Substitution("SU-1", "SU-9", "T-4471", DateRange.starting(date(2024, 1, 1)), ratio)]
    )


def test_a_complete_tray_counts_clean() -> None:
    result = count_tray(sheet(), {"SU-1": 4, "SU-2": 2, "SU-3": 1}, day=DAY)
    assert result.exact
    assert result.complete
    assert result.summary() == "ORT-MAJOR counts complete"


def test_a_missing_optional_item_does_not_stop_the_tray() -> None:
    result = count_tray(sheet(), {"SU-1": 4, "SU-2": 2}, day=DAY)
    assert result.exact
    assert result.complete


def test_a_shortage_is_blocking_and_names_the_gap() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-2": 2}, day=DAY)
    assert not result.complete
    assert [item.describe() for item in result.shortages()] == ["SU-1 short 1 of 4"]


def test_counts_are_normalised_and_added_up() -> None:
    result = count_tray(sheet(), [("su 1", 2), ("SU-1", 2), ("su_2", 2)], day=DAY)
    assert result.complete


def test_a_negative_count_is_refused() -> None:
    with pytest.raises(ValidationError):
        count_tray(sheet(), {"SU-1": -1}, day=DAY)


def test_an_extra_of_a_listed_item_is_reported_but_not_blocking() -> None:
    result = count_tray(sheet(), {"SU-1": 6, "SU-2": 2}, day=DAY)
    assert result.complete
    assert not result.exact
    assert result.discrepancies[0].describe() == "SU-1 has 2 more than the sheet"


def test_an_item_not_on_the_sheet_is_foreign() -> None:
    result = count_tray(sheet(), {"SU-1": 4, "SU-2": 2, "XX-9": 1}, day=DAY)
    assert result.complete
    assert [item.catalog for item in result.foreigns()] == ["XX-9"]
    assert result.discrepancies[0].describe() == "XX-9 is not on this sheet, 1 found"


def test_an_approved_replacement_covers_the_shortage() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-9": 1, "SU-2": 2}, table(), DAY)
    assert result.complete
    assert result.exact
    assert result.substitutions[0].describe() == "1 x SU-9 covering 1 x SU-1"


def test_the_same_replacement_without_an_approval_is_foreign() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-9": 1, "SU-2": 2}, SubstitutionTable(), DAY)
    assert not result.complete
    assert [item.catalog for item in result.foreigns()] == ["SU-9"]


def test_an_expired_approval_does_not_cover_anything() -> None:
    expired = SubstitutionTable.of(
        [Substitution("SU-1", "SU-9", "T-4471", DateRange(date(2024, 1, 1), date(2024, 3, 1)))]
    )
    result = count_tray(sheet(), {"SU-1": 3, "SU-9": 1, "SU-2": 2}, expired, DAY)
    assert not result.complete


def test_a_two_for_one_substitution_consumes_two() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-9": 2, "SU-2": 2}, table(ratio=2), DAY)
    assert result.exact
    assert result.substitutions[0].consumed == 2
    assert result.substitutions[0].covered == 1


def test_a_two_for_one_substitution_with_only_one_spare_covers_nothing() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-9": 1, "SU-2": 2}, table(ratio=2), DAY)
    assert not result.complete
    assert [item.catalog for item in result.foreigns()] == ["SU-9"]


def test_a_replacement_only_covers_what_it_was_approved_for() -> None:
    result = count_tray(sheet(), {"SU-1": 4, "SU-2": 1, "SU-9": 1}, table(), DAY)
    assert not result.complete
    assert [item.catalog for item in result.shortages()] == ["SU-2"]


def test_partly_covered_shortage_still_reports_what_is_left() -> None:
    result = count_tray(sheet(), {"SU-1": 2, "SU-9": 1, "SU-2": 2}, table(), DAY)
    shortage = result.shortages()[0]
    assert shortage.expected == 4
    assert shortage.found == 3
    assert result.substitutions[0].covered == 1


def test_leftover_replacements_are_still_foreign() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-9": 3, "SU-2": 2}, table(), DAY)
    assert result.complete
    assert result.foreigns()[0].found == 2


def test_summary_lists_every_difference() -> None:
    result = count_tray(sheet(), {"SU-1": 3, "SU-2": 3, "XX-1": 1}, day=DAY)
    assert result.summary() == (
        "ORT-MAJOR: SU-1 short 1 of 4; SU-2 has 1 more than the sheet; "
        "XX-1 is not on this sheet, 1 found"
    )
