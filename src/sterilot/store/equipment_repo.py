"""Reading and writing the machines.

Washers and sterilizers share one table because a great many questions are
about equipment in general: what is out of order, what is past qualification,
what ran today. The columns that only apply to one kind are nullable and the
kind column says which is which.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import NotFoundError, ValidationError
from sterilot.ids import equipment_id
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.sterilizer.equipment import ChamberSize, Sterilizer
from sterilot.store import rows
from sterilot.store.db import Database

STERILIZER = "sterilizer"
WASHER = "washer"

_COLUMNS = (
    "equipment_id, kind, model, manufacturer, detail, in_service, methods, chamber, chambers,"
    " installed_on, retired_on, out_of_order, qualification_owed, last_qualification"
)


@dataclass
class EquipmentStore:
    """Every machine in the department."""

    db: Database

    def save_sterilizer(self, unit: Sterilizer) -> None:
        window = unit.in_service
        self.db.execute(
            f"INSERT OR REPLACE INTO equipment ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                unit.equipment,
                STERILIZER,
                unit.model,
                unit.manufacturer,
                unit.notes,
                rows.put_bool(True),
                ",".join(sorted(method.value for method in unit.methods)),
                unit.chamber.value,
                1,
                rows.put_date(unit.installed_on),
                rows.put_date(None if window is None else window.end),
                rows.put_bool(unit.out_of_order),
                unit.qualification_runs_owed,
                None,
            ],
        )

    def save_washer(self, unit: Washer) -> None:
        window = unit.in_service
        self.db.execute(
            f"INSERT OR REPLACE INTO equipment ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                unit.equipment,
                WASHER,
                unit.model,
                unit.manufacturer,
                unit.washer_class.value,
                rows.put_bool(True),
                "",
                None,
                unit.chambers,
                rows.put_date(None if window is None else window.start),
                rows.put_date(None if window is None else window.end),
                rows.put_bool(unit.out_of_order),
                0,
                rows.put_date(unit.last_qualification),
            ],
        )

    def _row(self, equipment: str) -> sqlite3.Row:
        wanted = equipment_id(equipment)
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM equipment WHERE equipment_id = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("no machine with that identifier", equipment=wanted)
        return row

    def kind_of(self, equipment: str) -> str:
        return rows.get_text(self._row(equipment), "kind")

    def sterilizer(self, equipment: str) -> Sterilizer:
        row = self._row(equipment)
        if rows.get_text(row, "kind") != STERILIZER:
            raise ValidationError("that machine is not a sterilizer", equipment=equipment)
        return self._sterilizer(row)

    def _sterilizer(self, row: sqlite3.Row) -> Sterilizer:
        names = [name for name in rows.get_text_or_empty(row, "methods").split(",") if name]
        if not names:
            raise ValidationError("that sterilizer has no methods recorded")
        installed = rows.get_date_or_none(row, "installed_on")
        retired = rows.get_date_or_none(row, "retired_on")
        window = None
        if retired is not None:
            window = DateRange(installed or date(1970, 1, 1), retired)
        return Sterilizer(
            equipment=rows.get_text(row, "equipment_id"),
            model=rows.get_text(row, "model"),
            manufacturer=rows.get_text(row, "manufacturer"),
            methods=frozenset(Method.named(name) for name in names),
            chamber=ChamberSize.named(rows.get_text(row, "chamber")),
            installed_on=installed,
            in_service=window,
            out_of_order=rows.get_bool(row, "out_of_order"),
            qualification_runs_owed=rows.get_int(row, "qualification_owed"),
            notes=rows.get_text_or_empty(row, "detail"),
        )

    def washer(self, equipment: str) -> Washer:
        row = self._row(equipment)
        if rows.get_text(row, "kind") != WASHER:
            raise ValidationError("that machine is not a washer", equipment=equipment)
        return self._washer(row)

    def _washer(self, row: sqlite3.Row) -> Washer:
        installed = rows.get_date_or_none(row, "installed_on")
        retired = rows.get_date_or_none(row, "retired_on")
        window = None
        if retired is not None:
            window = DateRange(installed or date(1970, 1, 1), retired)
        return Washer(
            equipment=rows.get_text(row, "equipment_id"),
            model=rows.get_text(row, "model"),
            manufacturer=rows.get_text(row, "manufacturer"),
            washer_class=WasherClass.named(rows.get_text(row, "detail")),
            chambers=rows.get_int(row, "chambers"),
            in_service=window,
            last_qualification=rows.get_date_or_none(row, "last_qualification"),
            out_of_order=rows.get_bool(row, "out_of_order"),
        )

    def sterilizers(self) -> tuple[Sterilizer, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM equipment WHERE kind = ? ORDER BY equipment_id", [STERILIZER]
        )
        return tuple(self._sterilizer(row) for row in found)

    def washers(self) -> tuple[Washer, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM equipment WHERE kind = ? ORDER BY equipment_id", [WASHER]
        )
        return tuple(self._washer(row) for row in found)

    def exists(self, equipment: str) -> bool:
        wanted = equipment_id(equipment)
        return (
            self.db.scalar("SELECT 1 FROM equipment WHERE equipment_id = ?", [wanted]) is not None
        )

    def out_of_order(self) -> tuple[str, ...]:
        found = self.db.query(
            "SELECT equipment_id FROM equipment WHERE out_of_order = 1 ORDER BY equipment_id"
        )
        return tuple(str(row["equipment_id"]) for row in found)
