"""Reading and writing cleaning verification results."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.decon.verification import Verification, VerificationKind, VerificationLog
from sterilot.errors import ValidationError
from sterilot.ids import equipment_id
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = "equipment_id, at, kind, value, visual_pass, by_badge, lot, subject"


@dataclass
class VerificationStore:
    """Soil device, protein and ATP results."""

    db: Database

    def save(self, result: Verification) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO verification ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                result.equipment,
                rows.put_moment(result.at),
                result.kind.value,
                result.value,
                None if result.visual_pass is None else rows.put_bool(result.visual_pass),
                result.by,
                result.lot,
                result.subject,
            ],
        )

    def _build(self, row: sqlite3.Row) -> Verification:
        visual = row["visual_pass"]
        return Verification(
            kind=rows.get_enum(row, "kind", VerificationKind),
            equipment=rows.get_text(row, "equipment_id"),
            at=rows.get_moment(row, "at"),
            by=rows.get_text(row, "by_badge"),
            value=None if row["value"] is None else float(row["value"]),
            visual_pass=None if visual is None else bool(visual),
            lot=rows.get_text_or_empty(row, "lot"),
            subject=rows.get_text_or_empty(row, "subject"),
        )

    def for_equipment(self, equipment: str) -> tuple[Verification, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM verification WHERE equipment_id = ? ORDER BY at",
            [equipment_id(equipment)],
        )
        return tuple(self._build(row) for row in found)

    def on_day(self, equipment: str, day: date) -> tuple[Verification, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM verification WHERE equipment_id = ?"
            " AND at >= ? AND at < ? ORDER BY at",
            [equipment_id(equipment), *rows.day_window(day)],
        )
        return tuple(self._build(row) for row in found)

    def log(self, equipment: str | None = None) -> VerificationLog:
        if equipment is None:
            found = self.db.query(f"SELECT {_COLUMNS} FROM verification ORDER BY at")
            return VerificationLog.of(self._build(row) for row in found)
        return VerificationLog.of(self.for_equipment(equipment))

    def verified_on(self, equipment: str, day: date) -> bool:
        return any(
            item.kind is VerificationKind.SOIL_DEVICE and item.passed
            for item in self.on_day(equipment, day)
        )

    def suspect_window(self, equipment: str, at: datetime) -> tuple[datetime, datetime]:
        """The window a failure at ``at`` calls into question."""
        log = self.log(equipment)
        for item in log.for_equipment(equipment):
            if item.at == at and not item.passed:
                return log.suspect_window(equipment, item)
        raise ValidationError(
            "no failed verification at that moment", equipment=equipment_id(equipment)
        )
