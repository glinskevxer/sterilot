"""Reading and writing the daily test log."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.errors import NotFoundError
from sterilot.ids import equipment_id
from sterilot.quality.log import Duty, DutyLog, LogEntry
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = "day, equipment_id, duty, passed, by_badge, note"


@dataclass
class DutyStore:
    """The daily tests each machine owes."""

    db: Database

    def save(self, entry: LogEntry) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO duty_log ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
            [
                rows.put_date(entry.day),
                entry.equipment,
                entry.duty.value,
                rows.put_bool(entry.passed),
                entry.by,
                entry.note,
            ],
        )

    def _build(self, row: sqlite3.Row) -> LogEntry:
        return LogEntry(
            day=rows.get_date(row, "day"),
            equipment=rows.get_text(row, "equipment_id"),
            duty=rows.get_enum(row, "duty", Duty),
            passed=rows.get_bool(row, "passed"),
            by=rows.get_text(row, "by_badge"),
            note=rows.get_text_or_empty(row, "note"),
        )

    def get(self, equipment: str, day: date, duty: Duty) -> LogEntry:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM duty_log WHERE equipment_id = ? AND day = ? AND duty = ?",
            [equipment_id(equipment), rows.put_date(day), duty.value],
        )
        if row is None:
            raise NotFoundError(
                "that duty is not logged for the day",
                equipment=equipment_id(equipment),
                day=day.isoformat(),
            )
        return self._build(row)

    def on_day(self, equipment: str, day: date) -> tuple[LogEntry, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM duty_log WHERE equipment_id = ? AND day = ? ORDER BY duty",
            [equipment_id(equipment), rows.put_date(day)],
        )
        return tuple(self._build(row) for row in found)

    def between(self, start: date, end: date) -> DutyLog:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM duty_log WHERE day >= ? AND day < ?"
            " ORDER BY day, equipment_id",
            [rows.put_date(start), rows.put_date(end)],
        )
        return DutyLog.of(self._build(row) for row in found)

    def covered(self, equipment: str, day: date, duties: frozenset[Duty]) -> bool:
        done = {entry.duty for entry in self.on_day(equipment, day) if entry.passed}
        return duties <= done

    def air_removal_ok(self, equipment: str, day: date) -> bool:
        """Whether the chamber has a passing air removal test that day."""
        row = self.db.query_one(
            "SELECT passed FROM duty_log WHERE equipment_id = ? AND day = ? AND duty = ?",
            [equipment_id(equipment), rows.put_date(day), Duty.AIR_REMOVAL.value],
        )
        return row is not None and bool(row["passed"])

    def failures(self, start: date, end: date) -> tuple[LogEntry, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM duty_log WHERE passed = 0 AND day >= ? AND day < ?"
            " ORDER BY day, equipment_id",
            [rows.put_date(start), rows.put_date(end)],
        )
        return tuple(self._build(row) for row in found)
