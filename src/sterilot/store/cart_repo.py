"""Reading and writing case carts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.cases.cart import CartLine, CaseCart
from sterilot.errors import NotFoundError
from sterilot.ids import asset_tag, case_number, normalise_code
from sterilot.store import rows
from sterilot.store.db import Database

_CART = "reference, case_number, card_ref, built_by, built_at, delivered_at"
_LINE = "reference, asset, code, location, picked_by"


@dataclass
class CartStore:
    """Carts, and what was on them."""

    db: Database

    def save(self, cart: CaseCart) -> None:
        with self.db.transaction():
            self.db.execute(
                f"INSERT OR REPLACE INTO case_cart ({_CART}) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    cart.reference,
                    cart.case,
                    cart.card_reference,
                    cart.built_by,
                    rows.put_moment(cart.built_at),
                    rows.put_moment(cart.delivered_at),
                ],
            )
            self.db.execute("DELETE FROM case_cart_line WHERE reference = ?", [cart.reference])
            self.db.execute_many(
                f"INSERT INTO case_cart_line ({_LINE}) VALUES (?, ?, ?, ?, ?)",
                [
                    [cart.reference, line.asset, line.code, line.location, line.picked_by]
                    for line in cart.lines
                ],
            )

    def _build(self, row: sqlite3.Row) -> CaseCart:
        reference = rows.get_text(row, "reference")
        lines = tuple(
            CartLine(
                rows.get_text(item, "asset"),
                rows.get_text(item, "code"),
                rows.get_text_or_empty(item, "location"),
                rows.get_text_or_empty(item, "picked_by"),
            )
            for item in self.db.query(
                f"SELECT {_LINE} FROM case_cart_line WHERE reference = ? ORDER BY asset",
                [reference],
            )
        )
        return CaseCart(
            reference=reference,
            case=rows.get_text(row, "case_number"),
            card_reference=rows.get_text(row, "card_ref"),
            lines=lines,
            built_by=rows.get_text(row, "built_by"),
            built_at=rows.get_moment(row, "built_at"),
            delivered_at=rows.get_moment_or_none(row, "delivered_at"),
        )

    def get(self, reference: str) -> CaseCart:
        wanted = normalise_code(reference, field="cart reference")
        row = self.db.query_one(f"SELECT {_CART} FROM case_cart WHERE reference = ?", [wanted])
        if row is None:
            raise NotFoundError("no cart with that reference", reference=wanted)
        return self._build(row)

    def exists(self, reference: str) -> bool:
        wanted = normalise_code(reference, field="cart reference")
        return self.db.scalar("SELECT 1 FROM case_cart WHERE reference = ?", [wanted]) is not None

    def for_case(self, case: str) -> tuple[CaseCart, ...]:
        found = self.db.query(
            f"SELECT {_CART} FROM case_cart WHERE case_number = ? ORDER BY built_at",
            [case_number(case)],
        )
        return tuple(self._build(row) for row in found)

    def holding(self, asset: str) -> tuple[CaseCart, ...]:
        found = self.db.query(
            f"SELECT {_CART} FROM case_cart WHERE reference IN"
            " (SELECT reference FROM case_cart_line WHERE asset = ?) ORDER BY built_at",
            [asset_tag(asset)],
        )
        return tuple(self._build(row) for row in found)

    def built_on(self, day: date) -> tuple[CaseCart, ...]:
        start, end = rows.day_window(day)
        found = self.db.query(
            f"SELECT {_CART} FROM case_cart WHERE built_at >= ? AND built_at < ? ORDER BY built_at",
            [start, end],
        )
        return tuple(self._build(row) for row in found)

    def undelivered(self) -> tuple[CaseCart, ...]:
        found = self.db.query(
            f"SELECT {_CART} FROM case_cart WHERE delivered_at IS NULL ORDER BY built_at"
        )
        return tuple(self._build(row) for row in found)
