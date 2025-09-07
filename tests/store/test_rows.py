from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from sterilot.errors import IntegrityError
from sterilot.methods import Method
from sterilot.money import Money
from sterilot.store import rows
from sterilot.units.duration import Duration
from sterilot.units.mass import Mass
from sterilot.units.temperature import Temperature


def row(**values: object) -> sqlite3.Row:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    names = ", ".join(f"? AS {name}" for name in values)
    found = connection.execute(f"SELECT {names}", tuple(values.values())).fetchone()
    connection.close()
    assert isinstance(found, sqlite3.Row)
    return found


def test_dates_round_trip() -> None:
    assert rows.put_date(date(2024, 11, 1)) == "2024-11-01"
    assert rows.put_date(None) is None
    assert rows.get_date(row(day="2024-11-01"), "day") == date(2024, 11, 1)
    assert rows.get_date_or_none(row(day=None), "day") is None


def test_a_column_that_is_not_a_date_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_date(row(day="11/1/2024"), "day")


def test_moments_round_trip_to_the_second() -> None:
    moment = datetime(2024, 11, 1, 9, 30, 15, 400)
    stored = rows.put_moment(moment)
    assert stored == "2024-11-01T09:30:15"
    assert rows.get_moment(row(at=stored), "at") == datetime(2024, 11, 1, 9, 30, 15)
    assert rows.get_moment_or_none(row(at=None), "at") is None


def test_a_column_that_is_not_a_moment_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_moment(row(at="yesterday"), "at")


def test_flags_are_stored_as_one_and_zero() -> None:
    assert rows.put_bool(True) == 1
    assert rows.put_bool(False) == 0
    assert rows.get_bool(row(flag=1), "flag")
    assert not rows.get_bool(row(flag=0), "flag")


def test_a_flag_that_is_not_a_flag_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_bool(row(flag=7), "flag")


def test_enums_round_trip_by_value() -> None:
    assert rows.put_enum(Method.STEAM_PREVAC) == "steam_prevac"
    assert rows.put_enum(None) is None
    assert rows.get_enum(row(method="steam_prevac"), "method", Method) is Method.STEAM_PREVAC
    assert rows.get_enum_or_none(row(method=None), "method", Method) is None


def test_an_enum_value_we_do_not_know_is_refused() -> None:
    with pytest.raises(IntegrityError) as caught:
        rows.get_enum(row(method="microwave"), "method", Method)
    assert caught.value.context["kind"] == "Method"


def test_durations_are_stored_in_seconds() -> None:
    assert rows.put_seconds(Duration.of_minutes(4)) == pytest.approx(240.0)
    assert rows.put_seconds(None) is None
    assert rows.get_duration(row(seconds=240), "seconds").minutes == pytest.approx(4.0)
    assert rows.get_duration_or_zero(row(seconds=None), "seconds") == Duration.zero()


def test_masses_are_stored_in_grams() -> None:
    assert rows.put_grams(Mass.of_grams(600)) == pytest.approx(600.0)
    assert rows.put_grams(None) is None
    found = rows.get_mass_or_none(row(weight=600), "weight")
    assert found is not None
    assert found.grams == pytest.approx(600.0)
    assert rows.get_mass_or_none(row(weight=None), "weight") is None


def test_temperatures_are_stored_in_celsius() -> None:
    assert rows.put_celsius(Temperature(133.4)) == pytest.approx(133.4)
    assert rows.get_temperature(row(hold=133.4), "hold") == Temperature(133.4)
    assert rows.get_temperature_or_none(row(hold=None), "hold") is None


def test_a_temperature_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_temperature(row(hold="hot"), "hold")


def test_money_is_stored_in_cents() -> None:
    assert rows.put_money(Money(41235)) == 41235
    assert rows.put_money(None) is None
    found = rows.get_money_or_none(row(quote=41235), "quote")
    assert found == Money(41235)
    assert rows.get_money_or_none(row(quote=None), "quote") is None


def test_money_stored_as_a_float_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_money_or_none(row(quote=412.35), "quote")


def test_lists_round_trip_through_one_column() -> None:
    stored = rows.put_list(("first reason", "second reason"))
    assert rows.get_list(row(reasons=stored), "reasons") == ("first reason", "second reason")
    assert rows.get_list(row(reasons=""), "reasons") == ()
    assert rows.get_list(row(reasons=None), "reasons") == ()


def test_newlines_inside_a_reason_do_not_split_it() -> None:
    stored = rows.put_list(("a reason\nwith a break",))
    assert rows.get_list(row(reasons=stored), "reasons") == ("a reason with a break",)


def test_text_and_numbers() -> None:
    assert rows.get_text(row(name="ORT-0114"), "name") == "ORT-0114"
    assert rows.get_text_or_empty(row(name=None), "name") == ""
    assert rows.get_int(row(count=4), "count") == 4
    assert rows.get_int_or_none(row(count=None), "count") is None


def test_a_missing_required_text_column_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_text(row(name=None), "name")


def test_an_integer_column_holding_text_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_int(row(count="four"), "count")


def test_a_day_window_is_half_open() -> None:
    start, end = rows.day_window(date(2025, 4, 10))
    assert start == "2025-04-10T00:00:00"
    assert end == "2025-04-11T00:00:00"


def test_a_day_window_covers_the_last_second_of_the_day() -> None:
    start, end = rows.day_window(date(2025, 4, 10))
    assert start <= "2025-04-10T23:59:59" < end


def test_a_window_over_two_days_uses_the_same_boundary() -> None:
    start, end = rows.day_bounds(date(2025, 4, 1), date(2025, 4, 8))
    assert start == "2025-04-01T00:00:00"
    assert end == "2025-04-08T00:00:00"
    assert start <= "2025-04-07T23:59:59" < end


def test_a_date_column_holding_a_number_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_date(row(day=17), "day")


def test_a_duration_column_holding_text_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_duration(row(seconds="four"), "seconds")


def test_a_mass_column_holding_text_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_mass_or_none(row(weight="heavy"), "weight")


def test_an_enum_column_that_is_empty_is_refused() -> None:
    with pytest.raises(IntegrityError):
        rows.get_enum(row(method=None), "method", Method)
