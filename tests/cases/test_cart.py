from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.cases.cart import CartLine, CaseCart, Gap
from sterilot.cases.preference_card import CardLine, PreferenceCard
from sterilot.errors import ValidationError
from sterilot.interval import DateRange

BUILT = datetime(2024, 9, 3, 6, 30)


def card(**changes: object) -> PreferenceCard:
    values: dict[str, object] = {
        "reference": "PC-118",
        "surgeon": "Okonkwo",
        "procedure": "total knee revision",
        "lines": [
            CardLine("ORT-MAJOR", quantity=2),
            CardLine("GEN-MINOR", essential=False),
        ],
        "effective": DateRange.starting(date(2024, 1, 1)),
    }
    values.update(changes)
    return PreferenceCard.of(**values)  # type: ignore[arg-type]


def cart(
    assets: tuple[tuple[str, str], ...] = (
        ("ORT-0114", "ORT-MAJOR"),
        ("ORT-0115", "ORT-MAJOR"),
        ("GEN-0207", "GEN-MINOR"),
    ),
    **changes: object,
) -> CaseCart:
    values: dict[str, object] = {
        "reference": "cc 991",
        "case": "or3 20240903 01",
        "card_reference": "pc 118",
        "lines": [CartLine(asset, code, "ST-A1", "T-4471") for asset, code in assets],
        "built_by": "T-4471",
        "built_at": BUILT,
    }
    values.update(changes)
    return CaseCart.of(**values)  # type: ignore[arg-type]


def test_cart_identifiers_are_normalised() -> None:
    made = cart()
    assert made.reference == "CC-991"
    assert made.case == "OR3-20240903-01"
    assert made.card_reference == "PC-118"
    assert made.lines[0].location == "ST-A1"


def test_a_tray_cannot_be_on_the_cart_twice() -> None:
    with pytest.raises(ValidationError):
        cart(assets=(("ORT-0114", "ORT-MAJOR"), ("ort 0114", "ORT-MAJOR")))


def test_a_cart_cannot_be_delivered_before_it_is_built() -> None:
    with pytest.raises(ValidationError):
        cart(delivered_at=datetime(2024, 9, 3, 5, 0))


def test_a_matching_cart_has_no_gaps() -> None:
    made = cart()
    assert made.gaps(card()) == ()
    assert made.ready(card())
    assert made.summary(card()) == "CC-991 matches PC-118"


def test_counts_and_assets() -> None:
    made = cart()
    assert made.counts() == {"ORT-MAJOR": 2, "GEN-MINOR": 1}
    assert made.assets() == ("ORT-0114", "ORT-0115", "GEN-0207")


def test_a_cart_judged_against_the_wrong_card_is_refused() -> None:
    with pytest.raises(ValidationError):
        cart().gaps(card(reference="PC-119"))


def test_a_missing_essential_set_stops_the_case() -> None:
    made = cart(assets=(("ORT-0114", "ORT-MAJOR"), ("GEN-0207", "GEN-MINOR")))
    gaps = made.gaps(card())
    assert gaps[0].describe() == "ORT-MAJOR short 1 of 2 (essential)"
    assert not made.ready(card())
    assert made.blocking_gaps(card())


def test_a_missing_preferred_set_is_only_a_note() -> None:
    made = cart(assets=(("ORT-0114", "ORT-MAJOR"), ("ORT-0115", "ORT-MAJOR")))
    gaps = made.gaps(card())
    assert gaps[0].describe() == "GEN-MINOR short 1 of 1 (preferred)"
    assert made.ready(card())


def test_a_tray_nobody_asked_for_is_reported() -> None:
    made = cart(
        assets=(
            ("ORT-0114", "ORT-MAJOR"),
            ("ORT-0115", "ORT-MAJOR"),
            ("GEN-0207", "GEN-MINOR"),
            ("CYS-0001", "CYS-1"),
        )
    )
    gaps = made.gaps(card())
    assert gaps[0].describe() == "CYS-1 is on the cart and not on the card"
    assert made.ready(card())


def test_a_gap_reports_its_own_arithmetic() -> None:
    gap = Gap("ORT-MAJOR", 3, 1, True)
    assert gap.short == 2
    assert gap.blocking
    assert not Gap("ORT-MAJOR", 3, 3, True).blocking
    assert not Gap("GEN-MINOR", 1, 0, False).blocking


def test_delivery_is_recorded_once() -> None:
    delivered = cart().delivered_on(datetime(2024, 9, 3, 7, 0))
    assert delivered.delivered
    assert delivered.delivered_at == datetime(2024, 9, 3, 7, 0)
    with pytest.raises(ValidationError):
        delivered.delivered_on(datetime(2024, 9, 3, 8, 0))


def test_an_undelivered_cart_says_so() -> None:
    assert not cart().delivered


def test_the_summary_lists_every_gap() -> None:
    made = cart(assets=(("CYS-0001", "CYS-1"),))
    summary = made.summary(card())
    assert summary.startswith("CC-991: ORT-MAJOR short 2 of 2 (essential)")
    assert "CYS-1 is on the cart and not on the card" in summary
