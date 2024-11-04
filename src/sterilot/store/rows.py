"""Turning domain values into columns and back.

SQLite has five storage classes and the domain has dates, moments, enums,
booleans, durations, masses and money. Every repository would otherwise grow
its own slightly different conversion, and the one that is slightly different
is the one that writes a date as ``11/1/2024`` and breaks every range query in
the department.

Reads are strict. A column that will not convert raises rather than coming back
as None, because a silently missing sterilization temperature is worse than a
crash on the report that would have shown it.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar

from sterilot.errors import IntegrityError
from sterilot.money import Money
from sterilot.units.duration import Duration
from sterilot.units.mass import Mass
from sterilot.units.temperature import Temperature

EnumT = TypeVar("EnumT", bound=Enum)


def put_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def get_date(row: sqlite3.Row, column: str) -> date:
    value = _text(row, column)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise IntegrityError("that column is not a date", column=column, value=value) from exc


def get_date_or_none(row: sqlite3.Row, column: str) -> date | None:
    if row[column] is None:
        return None
    return get_date(row, column)


def put_moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(timespec="seconds")


def get_moment(row: sqlite3.Row, column: str) -> datetime:
    value = _text(row, column)
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise IntegrityError("that column is not a timestamp", column=column, value=value) from exc


def get_moment_or_none(row: sqlite3.Row, column: str) -> datetime | None:
    if row[column] is None:
        return None
    return get_moment(row, column)


def put_bool(value: bool) -> int:
    return 1 if value else 0


def get_bool(row: sqlite3.Row, column: str) -> bool:
    value = row[column]
    if value in (0, 1):
        return bool(value)
    raise IntegrityError("that column is not a flag", column=column, value=value)


def put_enum(value: Enum | None) -> str | None:
    return None if value is None else str(value.value)


def get_enum(row: sqlite3.Row, column: str, kind: type[EnumT]) -> EnumT:
    value = _text(row, column)
    for member in kind:
        if str(member.value) == value:
            return member
    raise IntegrityError(
        "that column is not a value we know", column=column, value=value, kind=kind.__name__
    )


def get_enum_or_none(row: sqlite3.Row, column: str, kind: type[EnumT]) -> EnumT | None:
    if row[column] is None:
        return None
    return get_enum(row, column, kind)


def put_seconds(value: Duration | None) -> float | None:
    return None if value is None else value.seconds


def get_duration(row: sqlite3.Row, column: str) -> Duration:
    return Duration(_number(row, column))


def get_duration_or_zero(row: sqlite3.Row, column: str) -> Duration:
    if row[column] is None:
        return Duration.zero()
    return get_duration(row, column)


def put_grams(value: Mass | None) -> float | None:
    return None if value is None else value.grams


def get_mass_or_none(row: sqlite3.Row, column: str) -> Mass | None:
    if row[column] is None:
        return None
    return Mass.of_grams(_number(row, column))


def put_celsius(value: Temperature | None) -> float | None:
    return None if value is None else value.celsius


def get_temperature(row: sqlite3.Row, column: str) -> Temperature:
    return Temperature(_number(row, column))


def get_temperature_or_none(row: sqlite3.Row, column: str) -> Temperature | None:
    if row[column] is None:
        return None
    return get_temperature(row, column)


def put_money(value: Money | None) -> int | None:
    return None if value is None else value.cents


def get_money_or_none(row: sqlite3.Row, column: str) -> Money | None:
    if row[column] is None:
        return None
    value = row[column]
    if not isinstance(value, int):
        raise IntegrityError("money is stored in whole cents", column=column, value=value)
    return Money(value)


def put_list(values: tuple[str, ...]) -> str:
    """Reasons and notes are stored as one newline separated blob."""
    return "\n".join(value.replace("\n", " ") for value in values)


def get_list(row: sqlite3.Row, column: str) -> tuple[str, ...]:
    value = row[column]
    if value is None or not str(value).strip():
        return ()
    return tuple(line for line in str(value).split("\n") if line)


def get_text(row: sqlite3.Row, column: str) -> str:
    return _text(row, column)


def get_text_or_empty(row: sqlite3.Row, column: str) -> str:
    value = row[column]
    return "" if value is None else str(value)


def get_int(row: sqlite3.Row, column: str) -> int:
    value = row[column]
    if not isinstance(value, int):
        raise IntegrityError("that column is not a whole number", column=column, value=value)
    return value


def get_int_or_none(row: sqlite3.Row, column: str) -> int | None:
    if row[column] is None:
        return None
    return get_int(row, column)


def _text(row: sqlite3.Row, column: str) -> str:
    value: Any = row[column]
    if value is None:
        raise IntegrityError("that column is empty and should not be", column=column)
    return str(value)


def _number(row: sqlite3.Row, column: str) -> float:
    value: Any = row[column]
    if not isinstance(value, int | float):
        raise IntegrityError("that column is not a number", column=column, value=value)
    return float(value)
