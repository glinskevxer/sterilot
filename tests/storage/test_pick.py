from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.settings import Settings
from sterilot.storage.event import Event, EventRecord, Package, Packaging
from sterilot.storage.pick import ShelfItem, oldest_first, on_hand, pick

NOW = datetime(2024, 9, 10, 8, 0)


def shelf_item(asset: str, month: int, code: str = "ORT-MAJOR", spoiled: bool = False) -> ShelfItem:
    sterilized = datetime(2024, month, 1, 9, 0)
    package = Package(
        asset,
        LotControlNumber("AC-1", date(2024, month, 1), 1),
        Packaging.SEQUENTIAL_WRAP,
        sterilized,
    )
    if spoiled:
        package = package.with_event(
            EventRecord(Event.TORN, datetime(2024, month, 15, 9, 0), "T-4471")
        )
    return ShelfItem(package, code, "ST-A1")


def test_identifiers_are_normalised() -> None:
    item = ShelfItem(shelf_item("ORT-0114", 3).package, "ort major", "st a1")
    assert item.code == "ORT-MAJOR"
    assert item.location == "ST-A1"
    assert item.asset == "ORT-0114"


def test_a_pick_asks_for_at_least_one() -> None:
    with pytest.raises(ValidationError):
        pick([], "ORT-MAJOR", 0, NOW)


def test_the_oldest_package_goes_first() -> None:
    shelf = [shelf_item("ORT-0114", 6), shelf_item("ORT-0115", 3), shelf_item("ORT-0116", 5)]
    result = pick(shelf, "ORT-MAJOR", 2, NOW)
    assert result.assets() == ("ORT-0115", "ORT-0116")
    assert result.complete


def test_packages_sterilized_together_are_ordered_by_tray() -> None:
    shelf = [shelf_item("ORT-0116", 3), shelf_item("ORT-0114", 3)]
    assert [item.asset for item in oldest_first(shelf)] == ["ORT-0114", "ORT-0116"]


def test_a_spoiled_package_is_skipped_with_its_reason() -> None:
    shelf = [shelf_item("ORT-0114", 3, spoiled=True), shelf_item("ORT-0115", 5)]
    result = pick(shelf, "ORT-MAJOR", 1, NOW)
    assert result.assets() == ("ORT-0115",)
    assert result.skipped[0].describe() == "ORT-0114: torn on 2024-03-15"


def test_a_short_pick_says_how_short() -> None:
    shelf = [shelf_item("ORT-0114", 3)]
    result = pick(shelf, "ORT-MAJOR", 3, NOW)
    assert not result.complete
    assert result.short == 2
    assert result.summary() == "ORT-MAJOR: picked 1 of 3, 2 short"


def test_a_complete_pick_reads_plainly() -> None:
    shelf = [shelf_item("ORT-0114", 3)]
    assert str(pick(shelf, "ORT-MAJOR", 1, NOW)) == "ORT-MAJOR: picked 1 of 1"


def test_another_set_on_the_same_shelf_is_ignored() -> None:
    shelf = [shelf_item("GEN-0207", 2, code="GEN-MINOR"), shelf_item("ORT-0114", 6)]
    result = pick(shelf, "ort major", 1, NOW)
    assert result.assets() == ("ORT-0114",)


def test_picking_stops_once_the_quantity_is_met() -> None:
    shelf = [shelf_item("ORT-0114", 3), shelf_item("ORT-0115", 4), shelf_item("ORT-0116", 5)]
    result = pick(shelf, "ORT-MAJOR", 2, NOW)
    assert len(result.picked) == 2
    assert result.skipped == ()


def test_a_shelf_life_setting_takes_old_stock_out_of_the_pick() -> None:
    shelf = [shelf_item("ORT-0114", 1), shelf_item("ORT-0115", 8)]
    result = pick(shelf, "ORT-MAJOR", 1, NOW, Settings(shelf_life_days=90))
    assert result.assets() == ("ORT-0115",)
    assert "shelf life" in result.skipped[0].reason


def test_on_hand_counts_only_what_is_usable() -> None:
    shelf = [
        shelf_item("ORT-0114", 3),
        shelf_item("ORT-0115", 4, spoiled=True),
        shelf_item("GEN-0207", 4, code="GEN-MINOR"),
    ]
    assert on_hand(shelf, NOW) == {"ORT-MAJOR": 1, "GEN-MINOR": 1}


def test_an_empty_shelf_counts_nothing_and_picks_nothing() -> None:
    assert on_hand([], NOW) == {}
    result = pick([], "ORT-MAJOR", 2, NOW)
    assert result.short == 2
    assert result.picked == ()
