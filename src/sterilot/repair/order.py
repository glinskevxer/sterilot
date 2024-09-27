"""Repair orders, and the fact that a tray is short until one comes back.

An instrument going out for repair is not a maintenance detail, it is a hole in
a count sheet for six weeks. So the order carries the tray it came out of, the
day it left, and what the vendor said it would cost, and the department can ask
which sets are running short because of the repair bench rather than finding
out at seven in the morning.

Approving a quote over the department's own threshold needs a supervisor, which
is the one rule in here that is about money rather than about instruments.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import asset_tag, badge_number, catalog_number, normalise_code, tray_code
from sterilot.money import Money
from sterilot.staff.tech import Role, Technician

APPROVAL_THRESHOLD = Money.of_dollars(500)
EXPECTED_TURNAROUND_DAYS = 21


class Status(Enum):
    """Where a repair order has got to."""

    RAISED = "raised"
    SENT = "sent"
    QUOTED = "quoted"
    APPROVED = "approved"
    RETURNED = "returned"
    SCRAPPED = "scrapped"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return self.value

    @property
    def closed(self) -> bool:
        return self in {Status.RETURNED, Status.SCRAPPED, Status.CANCELLED}

    @property
    def away(self) -> bool:
        """The instrument is not in the building."""
        return self in {Status.SENT, Status.QUOTED, Status.APPROVED}

    @classmethod
    def named(cls, value: str) -> Status:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such repair status", value=value)


_MOVES: dict[Status, frozenset[Status]] = {
    Status.RAISED: frozenset({Status.SENT, Status.CANCELLED}),
    Status.SENT: frozenset({Status.QUOTED, Status.RETURNED, Status.SCRAPPED}),
    Status.QUOTED: frozenset({Status.APPROVED, Status.SCRAPPED, Status.CANCELLED}),
    Status.APPROVED: frozenset({Status.RETURNED, Status.SCRAPPED}),
    Status.RETURNED: frozenset(),
    Status.SCRAPPED: frozenset(),
    Status.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class RepairOrder:
    """One instrument away for repair."""

    reference: str
    asset: str
    catalog: str
    tray_code_out_of: str
    vendor: str
    fault: str
    raised_at: datetime
    raised_by: str
    status: Status = Status.RAISED
    quote: Money | None = None
    approved_by: str = ""
    sent_at: datetime | None = None
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", normalise_code(self.reference, field="repair reference")
        )
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "catalog", catalog_number(self.catalog))
        object.__setattr__(self, "tray_code_out_of", tray_code(self.tray_code_out_of))
        object.__setattr__(self, "raised_by", badge_number(self.raised_by))
        if self.approved_by:
            object.__setattr__(self, "approved_by", badge_number(self.approved_by))
        if not self.vendor.strip():
            raise ValidationError("a repair goes to a vendor", reference=self.reference)
        if not self.fault.strip():
            raise ValidationError("a repair records the fault", reference=self.reference)
        if self.status is Status.APPROVED and self.quote is None:
            raise ValidationError("an approved repair has a quote", reference=self.reference)
        if self.status.closed and self.closed_at is None:
            raise ValidationError("a closed repair records when", reference=self.reference)

    @property
    def open(self) -> bool:
        return not self.status.closed

    def days_out(self, now: date) -> int | None:
        if self.sent_at is None:
            return None
        end = self.closed_at.date() if self.closed_at is not None else now
        return (end - self.sent_at.date()).days

    def overdue(self, now: date, allowed: int = EXPECTED_TURNAROUND_DAYS) -> bool:
        if not self.status.away:
            return False
        out = self.days_out(now)
        return out is not None and out > allowed

    def needs_supervisor(self) -> bool:
        return self.quote is not None and self.quote > APPROVAL_THRESHOLD

    def moved_to(self, status: Status, at: datetime, **values: object) -> RepairOrder:
        if status not in _MOVES[self.status]:
            raise ConflictError(
                "a repair cannot go there from here",
                reference=self.reference,
                current=self.status.value,
                target=status.value,
            )
        changes: dict[str, object] = {
            "reference": self.reference,
            "asset": self.asset,
            "catalog": self.catalog,
            "tray_code_out_of": self.tray_code_out_of,
            "vendor": self.vendor,
            "fault": self.fault,
            "raised_at": self.raised_at,
            "raised_by": self.raised_by,
            "status": status,
            "quote": self.quote,
            "approved_by": self.approved_by,
            "sent_at": at if status is Status.SENT else self.sent_at,
            "closed_at": at if status.closed else self.closed_at,
        }
        changes.update(values)
        return RepairOrder(**changes)  # type: ignore[arg-type]

    def approved(self, at: datetime, by: Technician, quote: Money) -> RepairOrder:
        """Approve a quote, which needs a supervisor over the threshold."""
        candidate = RepairOrder(
            self.reference,
            self.asset,
            self.catalog,
            self.tray_code_out_of,
            self.vendor,
            self.fault,
            self.raised_at,
            self.raised_by,
            self.status,
            quote,
        )
        if candidate.needs_supervisor() and by.role is not Role.SUPERVISOR:
            raise ConflictError(
                "a quote over the threshold needs a supervisor",
                reference=self.reference,
                quote=quote.format(),
            )
        return self.moved_to(Status.APPROVED, at, quote=quote, approved_by=by.badge)

    def summary(self) -> str:
        cost = f" {self.quote.format()}" if self.quote is not None else ""
        return f"{self.reference} {self.asset} {self.status.label}{cost}"

    def __str__(self) -> str:
        return self.summary()


@dataclass(frozen=True)
class RepairBook:
    """Every repair order the department has raised."""

    orders: tuple[RepairOrder, ...] = ()

    @classmethod
    def of(cls, orders: Iterable[RepairOrder]) -> RepairBook:
        return cls(tuple(orders))

    def with_order(self, order: RepairOrder) -> RepairBook:
        if any(item.reference == order.reference for item in self.orders):
            raise ConflictError("that repair reference is used", reference=order.reference)
        return RepairBook((*self.orders, order))

    def replacing(self, order: RepairOrder) -> RepairBook:
        if not any(item.reference == order.reference for item in self.orders):
            raise NotFoundError("no repair with that reference", reference=order.reference)
        return RepairBook(
            tuple(order if item.reference == order.reference else item for item in self.orders)
        )

    def get(self, reference: str) -> RepairOrder:
        wanted = normalise_code(reference, field="repair reference")
        for order in self.orders:
            if order.reference == wanted:
                return order
        raise NotFoundError("no repair with that reference", reference=wanted)

    def open_orders(self) -> tuple[RepairOrder, ...]:
        return tuple(order for order in self.orders if order.open)

    def away_from(self, code: str) -> tuple[RepairOrder, ...]:
        """Everything currently out of a given set, which is what shorts it."""
        wanted = tray_code(code)
        return tuple(
            order for order in self.orders if order.tray_code_out_of == wanted and order.status.away
        )

    def overdue(
        self, now: date, allowed: int = EXPECTED_TURNAROUND_DAYS
    ) -> tuple[RepairOrder, ...]:
        return tuple(order for order in self.orders if order.overdue(now, allowed))

    def spend(self) -> Money:
        return Money(
            sum(
                order.quote.cents
                for order in self.orders
                if order.quote is not None and order.status in {Status.APPROVED, Status.RETURNED}
            )
        )
