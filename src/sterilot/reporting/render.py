"""Plain text rendering.

Everything this department prints ends up either on a terminal or taped inside
a cupboard door, so the output is fixed width text with no colour and no box
drawing characters. A supervisor should be able to paste it into an email and
have it still line up.

Columns size themselves to their contents, numbers go right, everything else
goes left, and a cell that is too long is cut with an ellipsis rather than
wrapping, because a wrapped table stops being a table.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sterilot.errors import ValidationError

ELLIPSIS = "..."


@dataclass(frozen=True)
class Column:
    """One column of a table."""

    title: str
    align: str = "left"
    width: int | None = None

    def __post_init__(self) -> None:
        if self.align not in {"left", "right"}:
            raise ValidationError("a column is left or right aligned", align=self.align)
        if self.width is not None and self.width < 1:
            raise ValidationError("a column has width", width=self.width)


def clip(text: str, width: int) -> str:
    """Cut to ``width``, marking that something was cut."""
    if width < 1:
        raise ValidationError("nothing fits in no width", width=width)
    if len(text) <= width:
        return text
    if width <= len(ELLIPSIS):
        return text[:width]
    return text[: width - len(ELLIPSIS)] + ELLIPSIS


def table(columns: Sequence[Column], rows: Iterable[Sequence[object]], gap: int = 2) -> str:
    """Render a table. Every row must be as wide as the columns."""
    if not columns:
        raise ValidationError("a table has columns")
    if gap < 1:
        raise ValidationError("columns need a gap between them", gap=gap)
    body = [[_cell(value) for value in row] for row in rows]
    for row in body:
        if len(row) != len(columns):
            raise ValidationError(
                "that row does not match the columns", cells=len(row), columns=len(columns)
            )
    widths: list[int] = []
    for index, column in enumerate(columns):
        natural = max([len(column.title), *(len(row[index]) for row in body)])
        widths.append(column.width or natural)
    lines = [_line([column.title for column in columns], columns, widths, gap)]
    lines.append(_line(["-" * width for width in widths], columns, widths, gap))
    lines.extend(_line(row, columns, widths, gap) for row in body)
    return "\n".join(lines)


def _line(cells: Sequence[str], columns: Sequence[Column], widths: Sequence[int], gap: int) -> str:
    parts: list[str] = []
    for index, column in enumerate(columns):
        width = widths[index]
        text = clip(cells[index], width)
        parts.append(text.rjust(width) if column.align == "right" else text.ljust(width))
    return (" " * gap).join(parts).rstrip()


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def pairs(items: Iterable[tuple[str, object]], gap: int = 2) -> str:
    """A two column label and value block, for a header."""
    rows = [(label, _cell(value)) for label, value in items]
    if not rows:
        return ""
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label.ljust(width)}{' ' * gap}{value}" for label, value in rows)


def heading(text: str, underline: str = "=") -> str:
    if not text.strip():
        raise ValidationError("a heading has words in it")
    if len(underline) != 1:
        raise ValidationError("an underline is one character", underline=underline)
    return f"{text}\n{underline * len(text)}"


def bullets(items: Iterable[str], marker: str = "-") -> str:
    return "\n".join(f"{marker} {item}" for item in items)


def section(title: str, body: str, underline: str = "-") -> str:
    """A heading and a body, with nothing printed for an empty body."""
    if not body.strip():
        return heading(title, underline) + "\nnothing to report"
    return heading(title, underline) + "\n" + body


def join(blocks: Iterable[str]) -> str:
    """Stack blocks with one blank line between them."""
    kept = [block.rstrip() for block in blocks if block.strip()]
    return "\n\n".join(kept)
