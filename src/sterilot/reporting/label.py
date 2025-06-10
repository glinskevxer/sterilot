"""The label that goes on the package.

Everything a person holding a wrapped tray needs, on a piece of paper the width
of a label printer: what it is, which cycle made it, when, who assembled it,
and either the expiry or the sentence that says there is not one.

The lot control number is the important line. Everything else on the label is a
convenience, and that one is the whole audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber, asset_tag, badge_number, tray_code
from sterilot.methods import Method
from sterilot.settings import Settings
from sterilot.storage.event import Package

LABEL_WIDTH = 34


@dataclass(frozen=True)
class Label:
    """One package label."""

    asset: str
    code: str
    lot: LotControlNumber
    method: Method
    sterilized_at: datetime
    assembled_by: str
    expires_on: date | None = None
    facility: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "code", tray_code(self.code))
        object.__setattr__(self, "assembled_by", badge_number(self.assembled_by))
        if self.expires_on is not None and self.expires_on <= self.sterilized_at.date():
            raise ValidationError("a label cannot expire before it is printed", asset=self.asset)

    @property
    def expiry_line(self) -> str:
        if self.expires_on is None:
            return "sterile unless opened or damaged"
        return f"use by {self.expires_on.isoformat()}"

    def lines(self) -> tuple[str, ...]:
        head = self.facility[:LABEL_WIDTH] if self.facility else ""
        return tuple(
            line
            for line in (
                head,
                f"{self.code}  {self.asset}",
                self.lot.format(),
                f"{self.sterilized_at:%Y-%m-%d %H:%M}  {self.method.value}",
                f"assembled by {self.assembled_by}",
                self.expiry_line,
            )
            if line
        )

    def render(self) -> str:
        border = "-" * LABEL_WIDTH
        body = "\n".join(line[:LABEL_WIDTH] for line in self.lines())
        return f"{border}\n{body}\n{border}"

    def __str__(self) -> str:
        return self.render()


def for_package(
    package: Package,
    code: str,
    method: Method,
    assembled_by: str,
    settings: Settings | None = None,
) -> Label:
    """Build the label for a package on the shelf."""
    rules = settings or Settings()
    return Label(
        asset=package.asset,
        code=code,
        lot=package.lot,
        method=method,
        sterilized_at=package.sterilized_at,
        assembled_by=assembled_by,
        expires_on=package.expires_on(rules),
        facility=rules.facility,
    )


def sheet(labels: tuple[Label, ...], across: int = 1) -> str:
    """Several labels, one under another or side by side."""
    if across < 1:
        raise ValidationError("a sheet has at least one label across", across=across)
    if across == 1:
        return "\n".join(label.render() for label in labels)
    blocks = [label.render().splitlines() for label in labels]
    rendered: list[str] = []
    for start in range(0, len(blocks), across):
        row = blocks[start : start + across]
        height = max(len(block) for block in row)
        for index in range(height):
            cells = [
                block[index].ljust(LABEL_WIDTH) if index < len(block) else " " * LABEL_WIDTH
                for block in row
            ]
            rendered.append("  ".join(cells).rstrip())
    return "\n".join(rendered)
