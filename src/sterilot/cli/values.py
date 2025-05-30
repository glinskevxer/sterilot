"""Reading the little key and value options the commands take.

Half the commands here accept something like ``--line SU-1234=6:stringer 1``,
because a technician typing a set into a terminal will not type six options per
item. Every one of them was splitting the string its own way, and two of them
disagreed about whether the quantity was optional.
"""

from __future__ import annotations

from collections.abc import Iterable

from sterilot.errors import ValidationError


def pair(entry: str, separator: str = "=") -> tuple[str, str]:
    """Split ``KEY=VALUE`` into its two halves, with an empty value allowed."""
    key, found, value = entry.partition(separator)
    if not key.strip():
        raise ValidationError("that option has no name in front of it", entry=entry)
    return key.strip(), value.strip() if found else ""


def triple(entry: str) -> tuple[str, str, str]:
    """Split ``KEY=VALUE:EXTRA``, which is as far as this notation goes."""
    key, rest = pair(entry)
    value, _, extra = rest.partition(":")
    return key, value.strip(), extra.strip()


def whole(value: str, default: int = 1, *, field: str = "quantity") -> int:
    """Read a quantity, falling back to ``default`` when it was left off."""
    if not value:
        return default
    if not value.isdigit():
        raise ValidationError(f"that {field} is not a whole number", value=value)
    return int(value)


def tally(entries: Iterable[str]) -> dict[str, int]:
    """Add up ``CATALOG=QTY`` entries, letting a repeat mean more of the same."""
    counts: dict[str, int] = {}
    for entry in entries:
        key, value = pair(entry)
        counts[key] = counts.get(key, 0) + whole(value)
    return counts
