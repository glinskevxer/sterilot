from __future__ import annotations

import pytest
from click.testing import Result

from tests.cli.conftest import add_sterilizer, invoke, record_cycle

LOT = "AC-1-20250225-01"


@pytest.fixture
def store_room(db: str) -> str:
    add_sterilizer(db)
    record_cycle(db, "2025-02-25 08:00", run=1)
    invoke(
        db,
        "shelf",
        "add-location",
        "ST-A1",
        "rack A1",
        "--units",
        "24",
        "--floor-cm",
        "30",
        "--sprinkler-cm",
        "60",
    )
    return db


def put(db: str, asset: str, lot: str = LOT) -> Result:
    return invoke(db, "shelf", "put", asset, lot, "--location", "ST-A1", "--set", "ORT-MAJOR")


def test_a_good_location_saves_without_complaint(db: str) -> None:
    result = invoke(
        db,
        "shelf",
        "add-location",
        "ST-A1",
        "rack A1",
        "--units",
        "24",
        "--floor-cm",
        "30",
        "--sprinkler-cm",
        "60",
    )
    assert result.exit_code == 0
    assert "saved ST-A1 rack A1" in result.output
    assert result.output.strip().splitlines() == ["saved ST-A1 rack A1"]


def test_a_bad_location_saves_and_says_what_is_wrong(db: str) -> None:
    result = invoke(
        db,
        "shelf",
        "add-location",
        "ST-B1",
        "under the sink",
        "--units",
        "6",
        "--floor-cm",
        "10",
        "--sprinkler-cm",
        "20",
        "--under-plumbing",
    )
    assert result.exit_code == 0
    assert "under a sink" in result.output
    assert "off the floor" in result.output


def test_a_par_level_is_recorded(store_room: str) -> None:
    result = invoke(store_room, "shelf", "par", "ort major", "--minimum", "2", "--target", "5")
    assert result.exit_code == 0
    assert "ORT-MAJOR par 2 to 5" in result.output


def test_an_inverted_par_is_refused(store_room: str) -> None:
    result = invoke(store_room, "shelf", "par", "ORT-MAJOR", "--minimum", "5", "--target", "2")
    assert result.exit_code == 2


def test_a_package_goes_on_the_shelf(store_room: str) -> None:
    result = put(store_room, "ORT-0114")
    assert result.exit_code == 0
    assert f"ORT-0114 {LOT} on ST-A1" in result.output


def test_a_package_against_an_unknown_lot_exits_not_found(store_room: str) -> None:
    result = invoke(
        store_room,
        "shelf",
        "put",
        "ORT-0114",
        "AC-1-20250225-09",
        "--location",
        "ST-A1",
        "--set",
        "ORT-MAJOR",
    )
    assert result.exit_code == 3


def test_stock_shows_what_is_on_hand_and_what_to_build(store_room: str) -> None:
    invoke(store_room, "shelf", "par", "ORT-MAJOR", "--minimum", "2", "--target", "3")
    put(store_room, "ORT-0114")
    result = invoke(store_room, "shelf", "stock")
    assert "ORT-MAJOR" in result.output
    lines = [line for line in result.output.splitlines() if line.startswith("ORT-MAJOR")]
    assert lines[0].split()[-1] == "2"


def test_an_event_takes_a_pack_out_of_stock(store_room: str) -> None:
    put(store_room, "ORT-0114")
    result = invoke(store_room, "shelf", "event", "ORT-0114", LOT, "torn", "--note", "wrap torn")
    assert result.exit_code == 0
    assert "torn by T-4471, wrap torn" in result.output
    stock = invoke(store_room, "shelf", "stock")
    lines = [line for line in stock.output.splitlines() if line.startswith("ORT-MAJOR")]
    assert lines == []


def test_moving_a_pack_does_not_take_it_out_of_stock(store_room: str) -> None:
    put(store_room, "ORT-0114")
    invoke(store_room, "shelf", "event", "ORT-0114", LOT, "moved")
    stock = invoke(store_room, "shelf", "stock")
    assert "ORT-MAJOR" in stock.output


def test_picking_takes_a_pack_and_reports_it(store_room: str) -> None:
    put(store_room, "ORT-0114")
    result = invoke(store_room, "shelf", "pick", "ORT-MAJOR")
    assert result.exit_code == 0
    assert "picked 1 of 1" in result.output
    assert "ORT-0114" in result.output


def test_a_short_pick_exits_not_found(store_room: str) -> None:
    put(store_room, "ORT-0114")
    result = invoke(store_room, "shelf", "pick", "ORT-MAJOR", "--quantity", "3")
    assert result.exit_code == 3
    assert "2 short" in result.output


def test_a_pick_reports_what_it_skipped(store_room: str) -> None:
    put(store_room, "ORT-0114")
    invoke(store_room, "shelf", "event", "ORT-0114", LOT, "dropped", "--note", "on the dock")
    result = invoke(store_room, "shelf", "pick", "ORT-MAJOR")
    assert result.exit_code == 3
    assert "ORT-0114: dropped on" in result.output


def test_the_location_check_lists_what_is_unfit(store_room: str) -> None:
    invoke(
        store_room,
        "shelf",
        "add-location",
        "ST-B1",
        "under the sink",
        "--units",
        "6",
        "--floor-cm",
        "10",
        "--sprinkler-cm",
        "20",
        "--under-plumbing",
    )
    result = invoke(store_room, "shelf", "check")
    assert "usable capacity" in result.output
    assert "ST-B1 under the sink" in result.output
    assert "24" in result.output


def test_a_department_with_only_good_shelves_says_so(store_room: str) -> None:
    result = invoke(store_room, "shelf", "check")
    assert "every location is fit for storage" in result.output


def test_a_label_prints_for_a_package(store_room: str) -> None:
    put(store_room, "ORT-0114")
    result = invoke(store_room, "shelf", "label", "ORT-0114", LOT, "--set", "ORT-MAJOR")
    assert result.exit_code == 0
    assert LOT in result.output
    assert "ORT-MAJOR  ORT-0114" in result.output
    assert "sterile unless opened or damaged" in result.output


def test_several_copies_print(store_room: str) -> None:
    put(store_room, "ORT-0114")
    result = invoke(
        store_room, "shelf", "label", "ORT-0114", LOT, "--set", "ORT-MAJOR", "--copies", "3"
    )
    assert result.output.count(LOT) == 3


def test_a_label_for_an_unknown_package_exits_not_found(store_room: str) -> None:
    result = invoke(store_room, "shelf", "label", "ORT-9999", LOT, "--set", "ORT-MAJOR")
    assert result.exit_code == 3


def test_printing_no_copies_is_refused(store_room: str) -> None:
    put(store_room, "ORT-0114")
    result = invoke(
        store_room, "shelf", "label", "ORT-0114", LOT, "--set", "ORT-MAJOR", "--copies", "0"
    )
    assert result.exit_code != 0
