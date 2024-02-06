"""Identifiers, and the one place they are cleaned up.

Every identifier in the department arrives typed by hand, scanned off a label
that has been through a washer, or read out of a machine export that pads its
fields with spaces. If each module cleaned them up its own way then the same
tray would be two trays, which is exactly the failure the tracking system
exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sterilot.errors import ValidationError

_CODE_ALLOWED = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")
_SEPARATORS = re.compile(r"[\s_/.]+")
_REPEATED_DASH = re.compile(r"-{2,}")

LOT_CONTROL_PATTERN = re.compile(
    r"^(?P<sterilizer>[A-Z0-9\-]+)-(?P<date>\d{8})-(?P<run>\d{1,3})$",
)


def normalise_code(value: str, *, field: str, max_length: int = 32) -> str:
    """Upper case, collapse separators to a dash, and check the result.

    Empty input, a code that is nothing but punctuation, and a code longer than
    the label will hold are all refused here rather than three modules later.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text", field=field, value=value)
    cleaned = _SEPARATORS.sub("-", value.strip().upper())
    cleaned = _REPEATED_DASH.sub("-", cleaned).strip("-")
    if not cleaned:
        raise ValidationError(f"{field} is empty", field=field, value=value)
    if len(cleaned) > max_length:
        raise ValidationError(
            f"{field} is longer than the label will hold",
            field=field,
            value=cleaned,
            max_length=max_length,
        )
    if not _CODE_ALLOWED.match(cleaned):
        raise ValidationError(
            f"{field} has characters we cannot print on a label",
            field=field,
            value=cleaned,
        )
    return cleaned


def catalog_number(value: str) -> str:
    """A manufacturer catalog number, as it goes on the count sheet."""
    return normalise_code(value, field="catalog number", max_length=24)


def asset_tag(value: str) -> str:
    """The etched or engraved tag on a physical tray or container."""
    return normalise_code(value, field="asset tag", max_length=20)


def tray_code(value: str) -> str:
    """The department's short name for a set, such as ``ORT-MAJOR``."""
    return normalise_code(value, field="tray code", max_length=24)


def badge_number(value: str) -> str:
    """A technician badge, which is the signature on every record."""
    return normalise_code(value, field="badge number", max_length=12)


def case_number(value: str) -> str:
    """The surgical case a tray was issued to."""
    return normalise_code(value, field="case number", max_length=20)


def indicator_lot(value: str) -> str:
    """A biological or chemical indicator lot, off the box."""
    return normalise_code(value, field="indicator lot", max_length=20)


def equipment_id(value: str) -> str:
    """A washer or sterilizer, as the department numbers them."""
    return normalise_code(value, field="equipment id", max_length=16)


@dataclass(frozen=True, order=True)
class LotControlNumber:
    """What goes on every label in a load.

    Sterilizer, the date it ran, and which run of that day it was. Given a
    package pulled off a shelf two months later this is the whole audit trail:
    it names the cycle, and the cycle names the load, and the load names the
    contents.
    """

    sterilizer: str
    run_date: date
    run: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "sterilizer", equipment_id(self.sterilizer))
        if self.run < 1:
            raise ValidationError("run number starts at one", run=self.run)
        if self.run > 99:
            raise ValidationError("no sterilizer runs that many loads in a day", run=self.run)

    @classmethod
    def parse(cls, text: str) -> LotControlNumber:
        match = LOT_CONTROL_PATTERN.match(text.strip().upper())
        if match is None:
            raise ValidationError("cannot read that as a lot control number", text=text)
        raw = match.group("date")
        try:
            run_date = date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError as exc:
            raise ValidationError("lot control number has an impossible date", text=text) from exc
        return cls(match.group("sterilizer"), run_date, int(match.group("run")))

    def format(self) -> str:
        return f"{self.sterilizer}-{self.run_date:%Y%m%d}-{self.run:02d}"

    def __str__(self) -> str:
        return self.format()
