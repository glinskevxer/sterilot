"""Reading delimited files that were not written for us.

Every export in the department comes out of something old. The washer writes
tab separated with a byte order mark, the theatre system writes semicolons
because it was configured in Europe in 2011, and one of them pads every field
with spaces. None of that is interesting and all of it has to be handled, once,
here.

A read never stops at the first bad row. It collects what it can and reports
everything it could not, because a run of four hundred cycle records with two
bad lines should load three hundred and ninety eight of them and tell somebody
about the other two.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from sterilot.errors import ValidationError

DELIMITERS = (",", "\t", ";", "|")


@dataclass(frozen=True)
class Row:
    """One data row, with the line it came from."""

    number: int
    values: dict[str, str]

    def get(self, name: str, default: str = "") -> str:
        return self.values.get(name, default)

    def require(self, name: str) -> str:
        value = self.values.get(name, "").strip()
        if not value:
            raise ValidationError("that column is empty", row=self.number, column=name)
        return value

    def has(self, name: str) -> bool:
        return bool(self.values.get(name, "").strip())


@dataclass(frozen=True)
class RowProblem:
    """One row that could not be read."""

    number: int
    message: str
    detail: str = ""

    def describe(self) -> str:
        because = f": {self.detail}" if self.detail else ""
        return f"row {self.number} {self.message}{because}"


@dataclass(frozen=True)
class ReadResult:
    """What came out of a file."""

    rows: tuple[Row, ...] = ()
    problems: tuple[RowProblem, ...] = ()
    columns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        return f"{len(self.rows)} rows read, {len(self.problems)} rejected"


def sniff_delimiter(text: str) -> str:
    """Pick the delimiter that splits the header into the most fields."""
    header = _first_line(text)
    if header is None:
        raise ValidationError("the file has no header")
    counts = {delimiter: header.count(delimiter) for delimiter in DELIMITERS}
    best = max(counts, key=lambda item: counts[item])
    if counts[best] == 0:
        raise ValidationError("cannot tell what separates the columns", header=header)
    return best


def _first_line(text: str) -> str | None:
    for line in text.lstrip("﻿").splitlines():
        if line.strip():
            return line
    return None


def normalise_column(name: str) -> str:
    """Column names come back lower case with spaces and dots turned to underscores."""
    cleaned = name.strip().lstrip("﻿").lower()
    for character in (" ", "-", ".", "/"):
        cleaned = cleaned.replace(character, "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def read_delimited(
    text: str,
    required: Iterable[str] = (),
    aliases: Mapping[str, str] | None = None,
    delimiter: str | None = None,
) -> ReadResult:
    """Read a delimited file into rows, collecting rather than raising."""
    if not text.strip():
        raise ValidationError("the file is empty")
    separator = delimiter or sniff_delimiter(text)
    mapping = {normalise_column(key): value for key, value in (aliases or {}).items()}
    handle = io.StringIO(text.lstrip("﻿"))
    reader = csv.reader(handle, delimiter=separator)
    header: list[str] = []
    rows: list[Row] = []
    problems: list[RowProblem] = []
    for number, raw in enumerate(reader, start=1):
        if not any(cell.strip() for cell in raw):
            continue
        if not header:
            header = [mapping.get(normalise_column(cell), normalise_column(cell)) for cell in raw]
            missing = [name for name in required if name not in header]
            if missing:
                raise ValidationError("the file is missing columns", columns=missing)
            continue
        if len(raw) != len(header):
            problems.append(
                RowProblem(
                    number, "has the wrong number of fields", f"{len(raw)} not {len(header)}"
                )
            )
            continue
        values = {name: cell.strip() for name, cell in zip(header, raw, strict=True)}
        blank = [name for name in required if not values.get(name)]
        if blank:
            problems.append(RowProblem(number, "is missing values", ", ".join(blank)))
            continue
        rows.append(Row(number, values))
    return ReadResult(tuple(rows), tuple(problems), tuple(header))
