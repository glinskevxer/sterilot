from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.cases.cart import CartLine, CaseCart
from sterilot.cases.preference_card import CardLine, PreferenceCard
from sterilot.errors import NotFoundError
from sterilot.interval import DateRange
from sterilot.store.cart_repo import CartStore
from sterilot.store.store import Store

BUILT = datetime(2025, 4, 18, 6, 30)


@pytest.fixture
def carts() -> Iterator[CartStore]:
    store = Store.in_memory()
    yield store.carts
    store.close()


def cart(reference: str = "CC-991", assets: tuple[str, ...] = ("ORT-0114", "ORT-0115")) -> CaseCart:
    return CaseCart.of(
        reference,
        "OR3-01",
        "PC-118",
        [CartLine(asset, "ORT-MAJOR", "ST-A1", "T-4471") for asset in assets],
        "T-4471",
        BUILT,
    )


def card() -> PreferenceCard:
    return PreferenceCard.of(
        "PC-118",
        "Okonkwo",
        "total knee revision",
        [CardLine("ORT-MAJOR", quantity=2)],
        DateRange.starting(date(2025, 1, 1)),
    )


def test_a_cart_round_trips_with_its_lines(carts: CartStore) -> None:
    carts.save(cart())
    found = carts.get("cc 991")
    assert found.case == "OR3-01"
    assert found.assets() == ("ORT-0114", "ORT-0115")
    assert found.lines[0].location == "ST-A1"
    assert not found.delivered


def test_a_delivered_cart_keeps_its_time(carts: CartStore) -> None:
    carts.save(cart().delivered_on(datetime(2025, 4, 18, 7, 0)))
    found = carts.get("CC-991")
    assert found.delivered
    assert found.delivered_at == datetime(2025, 4, 18, 7, 0)


def test_an_unknown_cart_is_refused(carts: CartStore) -> None:
    with pytest.raises(NotFoundError):
        carts.get("CC-999")
    assert not carts.exists("CC-999")


def test_saving_again_replaces_the_lines(carts: CartStore) -> None:
    carts.save(cart())
    carts.save(cart(assets=("ORT-0116",)))
    assert carts.get("CC-991").assets() == ("ORT-0116",)


def test_the_cart_still_matches_its_card_after_a_round_trip(carts: CartStore) -> None:
    carts.save(cart())
    assert carts.get("CC-991").ready(card())
    carts.save(cart(assets=("ORT-0114",)))
    assert not carts.get("CC-991").ready(card())


def test_carts_are_found_by_case_and_by_tray(carts: CartStore) -> None:
    carts.save(cart("CC-991", ("ORT-0114",)))
    carts.save(cart("CC-992", ("ORT-0115",)))
    assert len(carts.for_case("OR3-01")) == 2
    assert [item.reference for item in carts.holding("ort 0114")] == ["CC-991"]
    assert carts.holding("XX-1") == ()


def test_carts_are_found_by_the_day_they_were_built(carts: CartStore) -> None:
    carts.save(cart())
    assert [item.reference for item in carts.built_on(date(2025, 4, 18))] == ["CC-991"]
    assert carts.built_on(date(2025, 4, 19)) == ()


def test_undelivered_carts_are_listed(carts: CartStore) -> None:
    carts.save(cart("CC-991"))
    carts.save(cart("CC-992").delivered_on(datetime(2025, 4, 18, 7, 0)))
    assert [item.reference for item in carts.undelivered()] == ["CC-991"]
