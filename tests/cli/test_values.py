from __future__ import annotations

import pytest

from sterilot.cli import values
from sterilot.errors import ValidationError


def test_a_pair_splits_on_the_first_separator() -> None:
    assert values.pair("SU-1234=6") == ("SU-1234", "6")
    assert values.pair("note=a=b") == ("note", "a=b")


def test_a_pair_with_no_value_comes_back_empty() -> None:
    assert values.pair("SU-1234") == ("SU-1234", "")
    assert values.pair("SU-1234=") == ("SU-1234", "")


def test_a_pair_is_stripped() -> None:
    assert values.pair("  SU-1234 = 6 ") == ("SU-1234", "6")


def test_a_pair_with_no_name_is_refused() -> None:
    with pytest.raises(ValidationError):
        values.pair("=6")


def test_another_separator_can_be_given() -> None:
    assert values.pair("wash:360", separator=":") == ("wash", "360")


def test_a_triple_splits_the_extra_off() -> None:
    assert values.triple("SU-1234=6:stringer 1") == ("SU-1234", "6", "stringer 1")
    assert values.triple("SU-1234=6") == ("SU-1234", "6", "")
    assert values.triple("SU-1234") == ("SU-1234", "", "")


def test_a_quantity_falls_back_when_it_is_left_off() -> None:
    assert values.whole("") == 1
    assert values.whole("", default=4) == 4
    assert values.whole("6") == 6


def test_a_quantity_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        values.whole("six", field="quantity")
    assert "quantity" in caught.value.message


def test_a_tally_adds_up_repeats() -> None:
    assert values.tally(["SU-1234=4", "SU-1234=2", "SU-1235"]) == {"SU-1234": 6, "SU-1235": 1}


def test_an_empty_tally_is_empty() -> None:
    assert values.tally([]) == {}
