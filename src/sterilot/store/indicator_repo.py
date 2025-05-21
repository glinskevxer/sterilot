"""The indicator lot register.

Every box of indicators in the department has a lot number and an expiry, and
using one past its date invalidates the result it gave. Keeping the register
means the load release can check the lot rather than trusting whoever read the
box, and the ordering list falls out of the same table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import indicator_lot
from sterilot.indicators.biological import BiologicalIndicator, Organism, Readout
from sterilot.indicators.chemical import ChemicalIndicator, IndicatorClass
from sterilot.methods import Method
from sterilot.store import rows
from sterilot.store.db import Database

CHEMICAL = "chemical"
BIOLOGICAL = "biological"

_COLUMNS = (
    "lot, family, detail, methods, expires_on, received_on, cycle_name, organism, readout, in_use"
)


@dataclass
class IndicatorStore:
    """Boxes of indicators, by lot."""

    db: Database

    def save_chemical(self, indicator: ChemicalIndicator, received_on: date | None = None) -> None:
        self._save(
            indicator.lot,
            CHEMICAL,
            indicator.indicator_class.value,
            indicator.methods,
            indicator.expires_on,
            received_on,
            cycle_name=indicator.cycle_name,
        )

    def save_biological(
        self, indicator: BiologicalIndicator, received_on: date | None = None
    ) -> None:
        methods = indicator.organism.methods
        self._save(
            indicator.lot,
            BIOLOGICAL,
            f"{indicator.population_log:.1f}",
            methods,
            indicator.expires_on,
            received_on,
            organism=indicator.organism.value,
            readout=indicator.readout.value,
        )

    def _save(
        self,
        lot: str,
        family: str,
        detail: str,
        methods: frozenset[Method],
        expires_on: date,
        received_on: date | None,
        cycle_name: str = "",
        organism: str = "",
        readout: str = "",
    ) -> None:
        existing = self.db.query_one("SELECT family FROM indicator_lot WHERE lot = ?", [lot])
        if existing is not None and rows.get_text(existing, "family") != family:
            raise ConflictError("that lot is already registered as another kind", lot=lot)
        self.db.execute(
            f"INSERT OR REPLACE INTO indicator_lot ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                lot,
                family,
                detail,
                ",".join(sorted(method.value for method in methods)),
                rows.put_date(expires_on),
                rows.put_date(received_on),
                cycle_name,
                organism,
                readout,
                rows.put_bool(True),
            ],
        )

    def chemical(self, lot: str) -> ChemicalIndicator:
        row = self._row(lot, CHEMICAL)
        return ChemicalIndicator(
            indicator_class=IndicatorClass.numbered(rows.get_text(row, "detail")),
            lot=rows.get_text(row, "lot"),
            expires_on=rows.get_date(row, "expires_on"),
            methods=self._methods(row),
            cycle_name=rows.get_text_or_empty(row, "cycle_name"),
        )

    def biological(self, lot: str) -> BiologicalIndicator:
        row = self._row(lot, BIOLOGICAL)
        return BiologicalIndicator(
            lot=rows.get_text(row, "lot"),
            organism=Organism.named(rows.get_text(row, "organism")),
            readout=Readout.named(rows.get_text(row, "readout")),
            expires_on=rows.get_date(row, "expires_on"),
            population_log=float(rows.get_text(row, "detail")),
        )

    def _row(self, lot: str, family: str) -> sqlite3.Row:
        wanted = indicator_lot(lot)
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM indicator_lot WHERE lot = ?", [wanted])
        if row is None:
            raise NotFoundError("no indicator lot with that number", lot=wanted)
        if rows.get_text(row, "family") != family:
            raise ValidationError("that lot is a different kind of indicator", lot=wanted)
        return row

    def _methods(self, row: sqlite3.Row) -> frozenset[Method]:
        names = [name for name in rows.get_text_or_empty(row, "methods").split(",") if name]
        return frozenset(Method.named(name) for name in names)

    def family_of(self, lot: str) -> str:
        wanted = indicator_lot(lot)
        row = self.db.query_one("SELECT family FROM indicator_lot WHERE lot = ?", [wanted])
        if row is None:
            raise NotFoundError("no indicator lot with that number", lot=wanted)
        return rows.get_text(row, "family")

    def in_date(self, lot: str, day: date) -> bool:
        wanted = indicator_lot(lot)
        row = self.db.query_one("SELECT expires_on FROM indicator_lot WHERE lot = ?", [wanted])
        if row is None:
            raise NotFoundError("no indicator lot with that number", lot=wanted)
        return day <= rows.get_date(row, "expires_on")

    def expiring(self, day: date, within_days: int) -> tuple[tuple[str, date], ...]:
        if within_days < 0:
            raise ValidationError("that is not a number of days", days=within_days)
        horizon = date.fromordinal(day.toordinal() + within_days)
        found = self.db.query(
            "SELECT lot, expires_on FROM indicator_lot WHERE in_use = 1 AND expires_on <= ?"
            " ORDER BY expires_on, lot",
            [rows.put_date(horizon)],
        )
        return tuple((rows.get_text(row, "lot"), rows.get_date(row, "expires_on")) for row in found)

    def retire(self, lot: str) -> None:
        wanted = indicator_lot(lot)
        self.db.execute("UPDATE indicator_lot SET in_use = 0 WHERE lot = ?", [wanted])

    def lots(self, family: str | None = None) -> tuple[str, ...]:
        if family is None:
            found = self.db.query("SELECT lot FROM indicator_lot ORDER BY lot")
        else:
            found = self.db.query(
                "SELECT lot FROM indicator_lot WHERE family = ? ORDER BY lot", [family]
            )
        return tuple(str(row["lot"]) for row in found)
