from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.money import Money, total


def test_cents_are_whole_numbers() -> None:
    assert Money(41235).cents == 41235
    with pytest.raises(ValidationError):
        Money(412.35)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Money(True)


def test_dollar_constructor() -> None:
    assert Money.of_dollars(412, 35) == Money(41235)
    assert Money.of_dollars(-412, 35) == Money(-41235)
    assert Money.zero() == Money(0)


def test_cents_out_of_range_are_refused() -> None:
    with pytest.raises(ValidationError):
        Money.of_dollars(4, 100)
    with pytest.raises(ValidationError):
        Money.of_dollars(4, -1)


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("412.35", 41235),
        ("$412.35", 41235),
        (" $ 1,204.00 ", 120400),
        ("19", 1900),
        ("-19.99", -1999),
        ("0.5", 50),
        ("0.05", 5),
    ],
)
def test_parse(text: str, cents: int) -> None:
    assert Money.parse(text).cents == cents


@pytest.mark.parametrize("text", ["", "free", "1.234", "$", "12,34.5"])
def test_parse_refuses_nonsense(text: str) -> None:
    with pytest.raises(ValidationError):
        Money.parse(text)


def test_dollars_and_sign() -> None:
    assert Money(41235).dollars == 412
    assert Money(-41235).dollars == -412
    assert Money(-1).negative
    assert not Money(0).negative


def test_arithmetic() -> None:
    assert Money(100) + Money(50) == Money(150)
    assert Money(100) - Money(150) == Money(-50)
    assert Money(100) * 3 == Money(300)
    assert -Money(100) == Money(-100)


def test_scaling_by_a_fraction_is_refused() -> None:
    with pytest.raises(ValidationError):
        Money(100) * 1.5  # type: ignore[operator]


def test_splitting_never_loses_a_cent() -> None:
    shares = Money(100).split(3)
    assert [share.cents for share in shares] == [34, 33, 33]
    assert total(shares) == Money(100)


def test_splitting_a_credit_keeps_the_sign() -> None:
    shares = Money(-100).split(3)
    assert [share.cents for share in shares] == [-34, -33, -33]
    assert total(shares) == Money(-100)


def test_splitting_fewer_than_one_way_is_refused() -> None:
    with pytest.raises(ValidationError):
        Money(100).split(0)


def test_allocation_follows_the_weights() -> None:
    shares = Money(10000).allocate([1, 1, 2])
    assert [share.cents for share in shares] == [2500, 2500, 5000]
    assert total(shares) == Money(10000)


def test_allocation_gives_the_remainder_to_the_largest_weight() -> None:
    shares = Money(100).allocate([1, 1, 1, 1, 1, 1, 1])
    assert total(shares) == Money(100)
    assert max(share.cents for share in shares) == 15


def test_allocating_a_credit_still_totals() -> None:
    shares = Money(-101).allocate([1, 1, 1])
    assert total(shares) == Money(-101)


def test_allocation_refuses_bad_weights() -> None:
    with pytest.raises(ValidationError):
        Money(100).allocate([])
    with pytest.raises(ValidationError):
        Money(100).allocate([1, -1])
    with pytest.raises(ValidationError):
        Money(100).allocate([0, 0])


def test_formatting() -> None:
    assert Money(41235).format() == "$412.35"
    assert Money(-1999).format() == "-$19.99"
    assert Money(120400).format() == "$1,204.00"
    assert str(Money(5)) == "$0.05"


def test_ordering_and_totals() -> None:
    assert Money(100) < Money(200)
    assert total([Money(100), Money(250)]) == Money(350)
    assert total([]) == Money.zero()
