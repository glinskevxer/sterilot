"""Vendor loaner sets, which are somebody else's problem until they are ours.

A loaner arrives from a manufacturer for one case, gets reprocessed here, used,
reprocessed again and sent back. Every part of that is a place to get hurt. The
set arrives at six in the evening for a seven in the morning case and there is
no time to run it. It arrives clean looking and somebody puts it straight on
the case cart. It goes back to the vendor soiled.

So a loaner is not a tray with a flag on it. It has its own arrival window, its
own count in, and its own rules about what may happen next.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import case_number, normalise_code
from sterilot.units.duration import Duration


class LoanerStage(Enum):
    """Where a loaner is in its visit."""

    EXPECTED = "expected"
    RECEIVED = "received"
    COUNTED = "counted"
    REPROCESSED = "reprocessed"
    RELEASED = "released"
    RETURNED = "returned"

    @property
    def label(self) -> str:
        return self.value

    @classmethod
    def named(cls, value: str) -> LoanerStage:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such loaner stage", value=value)


@dataclass(frozen=True)
class LoanerSet:
    """One vendor set, for one case."""

    reference: str
    vendor: str
    set_name: str
    case: str
    case_start: datetime
    expected_at: datetime
    received_at: datetime | None = None
    counted_at: datetime | None = None
    reprocessed_at: datetime | None = None
    released_at: datetime | None = None
    decontaminated_at: datetime | None = None
    returned_at: datetime | None = None
    piece_count: int | None = None
    rep_present_at_count: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="loaner reference")
        )
        object.__setattr__(self, "case", case_number(self.case))
        if not self.vendor.strip():
            raise ValidationError("a loaner needs a vendor", reference=self.reference)
        if not self.set_name.strip():
            raise ValidationError("a loaner needs a set name", reference=self.reference)
        if self.expected_at > self.case_start:
            raise ValidationError(
                "a loaner cannot be expected after the case starts", reference=self.reference
            )
        if self.piece_count is not None and self.piece_count < 1:
            raise ValidationError("a counted loaner has pieces in it", reference=self.reference)
        order = [
            ("received", self.received_at),
            ("counted", self.counted_at),
            ("reprocessed", self.reprocessed_at),
            ("released", self.released_at),
            ("decontaminated", self.decontaminated_at),
            ("returned", self.returned_at),
        ]
        seen: datetime | None = None
        for name, moment in order:
            if moment is None:
                continue
            if seen is not None and moment < seen:
                raise ValidationError(
                    "loaner milestones are out of order",
                    reference=self.reference,
                    milestone=name,
                )
            seen = moment

    @property
    def stage(self) -> LoanerStage:
        if self.returned_at is not None:
            return LoanerStage.RETURNED
        if self.released_at is not None:
            return LoanerStage.RELEASED
        if self.reprocessed_at is not None:
            return LoanerStage.REPROCESSED
        if self.counted_at is not None:
            return LoanerStage.COUNTED
        if self.received_at is not None:
            return LoanerStage.RECEIVED
        return LoanerStage.EXPECTED

    def lead_time(self) -> Duration | None:
        """How long before the case the set actually landed."""
        if self.received_at is None:
            return None
        gap = (self.case_start - self.received_at).total_seconds()
        return Duration(max(gap, 0.0))

    def arrived_in_time(self, lead_hours: int) -> bool:
        lead = self.lead_time()
        if lead is None:
            return False
        return lead.hours >= lead_hours

    def deadline(self, lead_hours: int) -> datetime:
        return self.case_start - timedelta(hours=lead_hours)

    def problems(self, lead_hours: int) -> tuple[str, ...]:
        """Everything wrong with this loaner right now, in the order it matters."""
        found: list[str] = []
        if self.received_at is None:
            found.append("the set has not arrived")
            return tuple(found)
        if not self.arrived_in_time(lead_hours):
            found.append(f"the set arrived inside the {lead_hours} hour window")
        if self.counted_at is None:
            found.append("the set has not been counted in")
        elif not self.rep_present_at_count:
            found.append("the count was taken without the vendor representative")
        if self.piece_count is None:
            found.append("no piece count was recorded")
        if self.reprocessed_at is None:
            found.append("the set has not been reprocessed here")
        return tuple(found)

    def ready_for_case(self, lead_hours: int) -> bool:
        return not self.problems(lead_hours)

    def may_return(self) -> str | None:
        """Why the set cannot go back to the vendor yet, or None."""
        if self.released_at is None:
            return "the set has not been released to the case"
        if self.decontaminated_at is None:
            return "the set has to be decontaminated after the case"
        return None

    def label(self) -> str:
        return f"{self.reference} {self.set_name} for {self.case}"

    def __str__(self) -> str:
        return self.label()
