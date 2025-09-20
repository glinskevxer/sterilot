"""Reading and writing repair orders."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.errors import ConflictError, NotFoundError
from sterilot.ids import asset_tag, normalise_code, tray_code
from sterilot.repair.order import RepairBook, RepairOrder, Status
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = (
    "reference, asset, catalog, out_of_code, vendor, fault, raised_at, raised_by, status,"
    " quote_cents, approved_by, sent_at, closed_at"
)


@dataclass
class RepairStore:
    """Instruments away for repair."""

    db: Database

    def save(self, order: RepairOrder) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO repair_order ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                order.reference,
                order.asset,
                order.catalog,
                order.tray_code_out_of,
                order.vendor,
                order.fault,
                rows.put_moment(order.raised_at),
                order.raised_by,
                order.status.value,
                rows.put_money(order.quote),
                order.approved_by,
                rows.put_moment(order.sent_at),
                rows.put_moment(order.closed_at),
            ],
        )

    def add(self, order: RepairOrder) -> None:
        """Raise a new order, refusing a reference already in use."""
        if self.exists(order.reference):
            raise ConflictError("that repair reference is used", reference=order.reference)
        self.save(order)

    def _build(self, row: sqlite3.Row) -> RepairOrder:
        return RepairOrder(
            reference=rows.get_text(row, "reference"),
            asset=rows.get_text(row, "asset"),
            catalog=rows.get_text(row, "catalog"),
            tray_code_out_of=rows.get_text(row, "out_of_code"),
            vendor=rows.get_text(row, "vendor"),
            fault=rows.get_text(row, "fault"),
            raised_at=rows.get_moment(row, "raised_at"),
            raised_by=rows.get_text(row, "raised_by"),
            status=rows.get_enum(row, "status", Status),
            quote=rows.get_money_or_none(row, "quote_cents"),
            approved_by=rows.get_text_or_empty(row, "approved_by"),
            sent_at=rows.get_moment_or_none(row, "sent_at"),
            closed_at=rows.get_moment_or_none(row, "closed_at"),
        )

    def get(self, reference: str) -> RepairOrder:
        wanted = normalise_code(reference, field="repair reference")
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM repair_order WHERE reference = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("no repair with that reference", reference=wanted)
        return self._build(row)

    def exists(self, reference: str) -> bool:
        wanted = normalise_code(reference, field="repair reference")
        return (
            self.db.scalar("SELECT 1 FROM repair_order WHERE reference = ?", [wanted]) is not None
        )

    def open_orders(self) -> tuple[RepairOrder, ...]:
        closed = ", ".join(f"'{status.value}'" for status in Status if status.closed)
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM repair_order WHERE status NOT IN ({closed}) ORDER BY raised_at"
        )
        return tuple(self._build(row) for row in found)

    def away_from(self, code: str) -> tuple[RepairOrder, ...]:
        away = ", ".join(f"'{status.value}'" for status in Status if status.away)
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM repair_order WHERE out_of_code = ? AND status IN ({away})"
            " ORDER BY raised_at",
            [tray_code(code)],
        )
        return tuple(self._build(row) for row in found)

    def for_asset(self, asset: str) -> tuple[RepairOrder, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM repair_order WHERE asset = ? ORDER BY raised_at",
            [asset_tag(asset)],
        )
        return tuple(self._build(row) for row in found)

    def book(self) -> RepairBook:
        found = self.db.query(f"SELECT {_COLUMNS} FROM repair_order ORDER BY raised_at")
        return RepairBook.of(self._build(row) for row in found)

    def overdue(self, today: date) -> tuple[RepairOrder, ...]:
        return tuple(order for order in self.open_orders() if order.overdue(today))
