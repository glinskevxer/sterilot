"""Reading and writing the planned maintenance schedule."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.errors import NotFoundError
from sterilot.ids import equipment_id, normalise_code
from sterilot.sterilizer.maintenance import Plan, Task
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = "code, equipment_id, description, every_days, every_cycles, last_done, cycles_since"


@dataclass
class MaintenanceStore:
    """Planned jobs and how far off each one is."""

    db: Database

    def save(self, task: Task) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO maintenance_task ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                task.code,
                task.equipment,
                task.description,
                task.every_days,
                task.every_cycles,
                rows.put_date(task.last_done),
                task.cycles_since,
            ],
        )

    def _build(self, row: sqlite3.Row) -> Task:
        return Task(
            code=rows.get_text(row, "code"),
            equipment=rows.get_text(row, "equipment_id"),
            description=rows.get_text(row, "description"),
            every_days=rows.get_int_or_none(row, "every_days"),
            every_cycles=rows.get_int_or_none(row, "every_cycles"),
            last_done=rows.get_date_or_none(row, "last_done"),
            cycles_since=rows.get_int(row, "cycles_since"),
        )

    def get(self, equipment: str, code: str) -> Task:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM maintenance_task WHERE equipment_id = ? AND code = ?",
            [equipment_id(equipment), normalise_code(code, field="task code")],
        )
        if row is None:
            raise NotFoundError(
                "no such maintenance task", equipment=equipment_id(equipment), code=code
            )
        return self._build(row)

    def plan(self) -> Plan:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM maintenance_task ORDER BY equipment_id, code"
        )
        return Plan.of(self._build(row) for row in found)

    def for_equipment(self, equipment: str) -> tuple[Task, ...]:
        return self.plan().for_equipment(equipment)

    def done(self, equipment: str, code: str, day: date) -> Task:
        task = self.get(equipment, code).done(day)
        self.save(task)
        return task

    def after_cycle(self, equipment: str) -> tuple[Task, ...]:
        """Count one cycle against every cycle driven task on a machine."""
        changed: list[Task] = []
        with self.db.transaction():
            for task in self.for_equipment(equipment):
                if task.every_cycles is None:
                    continue
                grown = task.after_cycle()
                self.save(grown)
                changed.append(grown)
        return tuple(changed)

    def due(self, day: date) -> tuple[Task, ...]:
        return self.plan().due(day)

    def coming(self, day: date, within_days: int) -> tuple[Task, ...]:
        return self.plan().coming(day, within_days)
