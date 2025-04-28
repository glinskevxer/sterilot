from __future__ import annotations

import pytest

from tests.cli.conftest import add_sterilizer, invoke, record_cycle

LOT = "AC-1-20250421-01"


@pytest.fixture
def floor(db: str) -> str:
    add_sterilizer(db)
    record_cycle(db, "2025-04-21 06:00", run=1)
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
    for asset in ("ORT-0114", "ORT-0115"):
        invoke(db, "shelf", "put", asset, LOT, "--location", "ST-A1", "--set", "ORT-MAJOR")
    invoke(
        db,
        "schedule",
        "add-card",
        "PC-118",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--line",
        "ORT-MAJOR=2",
        "--from",
        "2025-01-01",
    )
    invoke(
        db,
        "schedule",
        "add-case",
        "OR3-01",
        "--room",
        "OR3",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--start",
        "2025-04-21 08:00",
        "--minutes",
        "120",
        "--card",
        "PC-118",
    )
    return db


def test_a_cart_builds_from_the_shelf(floor: str) -> None:
    result = invoke(floor, "cart", "build", "CC-991", "OR3-01")
    assert result.exit_code == 0
    assert "CC-991 matches PC-118" in result.output


def test_a_short_shelf_leaves_the_cart_short(floor: str) -> None:
    invoke(floor, "shelf", "event", "ORT-0115", LOT, "torn", "--note", "wrap torn")
    result = invoke(floor, "cart", "build", "CC-991", "OR3-01")
    assert result.exit_code == 5
    assert "ORT-MAJOR short 1 of 2 (essential)" in result.output
    assert "came up 1 short" in result.output


def test_a_case_with_no_card_is_refused(floor: str) -> None:
    invoke(
        floor,
        "schedule",
        "add-case",
        "OR4-01",
        "--room",
        "OR4",
        "--surgeon",
        "Bell",
        "--procedure",
        "cysto",
        "--start",
        "2025-04-21 09:00",
        "--minutes",
        "45",
    )
    result = invoke(floor, "cart", "build", "CC-992", "OR4-01")
    assert result.exit_code != 0
    assert "has no preference card" in result.output


def test_a_cart_can_be_topped_up(floor: str) -> None:
    invoke(floor, "shelf", "event", "ORT-0115", LOT, "torn", "--note", "wrap torn")
    invoke(floor, "cart", "build", "CC-991", "OR3-01")
    invoke(floor, "tray", "register", "ORT-0116", "ORT-MAJOR")
    result = invoke(floor, "cart", "add", "CC-991", "--tray", "ORT-0116")
    assert result.exit_code == 0
    assert "now carries 2 trays" in result.output
    checked = invoke(floor, "cart", "check", "CC-991")
    assert checked.exit_code == 0


def test_the_check_reports_a_tray_nobody_asked_for(floor: str) -> None:
    invoke(floor, "cart", "build", "CC-991", "OR3-01")
    invoke(floor, "tray", "register", "CYS-0001", "CYS-1")
    invoke(floor, "cart", "add", "CC-991", "--tray", "CYS-0001")
    result = invoke(floor, "cart", "check", "CC-991")
    assert result.exit_code == 0
    assert "CYS-1 is on the cart and not on the card" in result.output


def test_a_cart_is_delivered_once(floor: str) -> None:
    invoke(floor, "cart", "build", "CC-991", "OR3-01")
    first = invoke(floor, "cart", "deliver", "CC-991")
    assert first.exit_code == 0
    assert "delivered to OR3-01" in first.output
    second = invoke(floor, "cart", "deliver", "CC-991")
    assert second.exit_code == 2


def test_show_lists_what_is_on_the_cart(floor: str) -> None:
    invoke(floor, "cart", "build", "CC-991", "OR3-01")
    result = invoke(floor, "cart", "show", "CC-991")
    assert "ORT-0114" in result.output
    assert "ST-A1" in result.output
    assert "delivered" in result.output


def test_waiting_lists_the_undelivered_carts(floor: str) -> None:
    invoke(floor, "cart", "build", "CC-991", "OR3-01")
    waiting = invoke(floor, "cart", "waiting")
    assert "CC-991" in waiting.output
    invoke(floor, "cart", "deliver", "CC-991")
    after = invoke(floor, "cart", "waiting")
    assert "CC-991" not in after.output


def test_an_unknown_cart_exits_not_found(floor: str) -> None:
    assert invoke(floor, "cart", "show", "CC-999").exit_code == 3
