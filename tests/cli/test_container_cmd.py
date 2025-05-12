from __future__ import annotations

import pytest

from tests.cli.conftest import invoke


@pytest.fixture
def store_room(db: str) -> str:
    invoke(
        db,
        "container",
        "add",
        "RC-2001",
        "--model",
        "Genesis 23x11",
        "--manufacturer",
        "Aesculap",
        "--inspected",
        "2026-08-01",
    )
    return db


def test_a_container_registers(db: str) -> None:
    result = invoke(
        db,
        "container",
        "add",
        "rc 2001",
        "--model",
        "Genesis 23x11",
        "--manufacturer",
        "Aesculap",
    )
    assert result.exit_code == 0
    assert "registered RC-2001 Genesis 23x11" in result.output


def test_an_unknown_filter_type_is_refused(db: str) -> None:
    result = invoke(
        db, "container", "add", "RC-1", "--model", "x", "--manufacturer", "y", "--filter", "cloth"
    )
    assert result.exit_code == 2


def test_show_says_what_it_can_run(store_room: str) -> None:
    result = invoke(store_room, "container", "show", "RC-2001")
    assert result.exit_code == 0
    assert "filters per cycle" in result.output
    assert "steam_prevac" in result.output
    assert "ready" in result.output


def test_a_paper_filter_keeps_it_out_of_peroxide(db: str) -> None:
    invoke(
        db,
        "container",
        "add",
        "RC-2002",
        "--model",
        "Genesis",
        "--manufacturer",
        "Aesculap",
        "--filter",
        "paper",
        "--inspected",
        "2026-08-01",
    )
    result = invoke(db, "container", "show", "RC-2002")
    assert "vaporized hydrogen peroxide: paper filters are cellulose" in result.output


def test_a_cycle_moves_it_toward_inspection(store_room: str) -> None:
    result = invoke(store_room, "container", "used", "RC-2001")
    assert "has run 1 cycles" in result.output


def test_an_inspection_can_record_damage(store_room: str) -> None:
    result = invoke(store_room, "container", "inspect", "RC-2001", "--gasket-damaged")
    assert result.exit_code == 0
    assert "the gasket does not seal" in result.output
    shown = invoke(store_room, "container", "show", "RC-2001")
    assert "the gasket does not seal" in shown.output


def test_a_clean_inspection_says_nothing_more(store_room: str) -> None:
    result = invoke(store_room, "container", "inspect", "RC-2001")
    assert result.output.strip() == "RC-2001 inspected"


def test_the_list_shows_every_container(store_room: str) -> None:
    result = invoke(store_room, "container", "list")
    assert "RC-2001" in result.output
    assert "disposable synthetic" in result.output


def test_nothing_due_says_so(store_room: str) -> None:
    result = invoke(store_room, "container", "due")
    assert "nothing is due" in result.output


def test_a_container_never_inspected_is_due(db: str) -> None:
    invoke(db, "container", "add", "RC-2003", "--model", "x", "--manufacturer", "y")
    result = invoke(db, "container", "due")
    assert "RC-2003" in result.output
    assert "never" in result.output


def test_the_filter_count_adds_up(store_room: str) -> None:
    invoke(
        db_or := store_room,
        "container",
        "add",
        "RC-2004",
        "--model",
        "x",
        "--manufacturer",
        "y",
        "--vents",
        "4",
        "--inspected",
        "2026-08-01",
    )
    result = invoke(db_or, "container", "filters")
    assert "filters per turn" in result.output
    assert "6" in result.output


def test_an_unknown_container_exits_not_found(db: str) -> None:
    assert invoke(db, "container", "show", "RC-9999").exit_code == 3
