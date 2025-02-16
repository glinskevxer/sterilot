"""Reading and writing the roster and the competency file."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.errors import NotFoundError
from sterilot.ids import badge_number
from sterilot.interval import DateRange
from sterilot.staff.competency import Competency, CompetencyFile, Task
from sterilot.staff.tech import Certification, Role, Roster, Technician
from sterilot.store import rows
from sterilot.store.db import Database

_PERSON = "badge, name, role, starts_on, ends_on"
_CERT = "badge, body, number, starts_on, ends_on"
_COMPETENCY = "badge, task, assessed_on, assessor, observations, valid_until"


@dataclass
class StaffStore:
    """People, their certifications and what they are signed off to do."""

    db: Database

    def save(self, person: Technician) -> None:
        window = person.employed
        with self.db.transaction():
            self.db.execute(
                f"INSERT OR REPLACE INTO technician ({_PERSON}) VALUES (?, ?, ?, ?, ?)",
                [
                    person.badge,
                    person.name,
                    person.role.value,
                    rows.put_date(None if window is None else window.start),
                    rows.put_date(None if window is None else window.end),
                ],
            )
            self.db.execute("DELETE FROM certification WHERE badge = ?", [person.badge])
            self.db.execute_many(
                f"INSERT INTO certification ({_CERT}) VALUES (?, ?, ?, ?, ?)",
                [
                    [
                        person.badge,
                        item.body,
                        item.number,
                        rows.put_date(item.held.start),
                        rows.put_date(item.held.end),
                    ]
                    for item in person.certifications
                ],
            )

    def _person(self, row: sqlite3.Row) -> Technician:
        badge = rows.get_text(row, "badge")
        starts = rows.get_date_or_none(row, "starts_on")
        ends = rows.get_date_or_none(row, "ends_on")
        window = None
        if starts is not None or ends is not None:
            window = DateRange(starts or date(1970, 1, 1), ends)
        certifications = tuple(
            Certification(
                rows.get_text(item, "body"),
                rows.get_text(item, "number"),
                DateRange(rows.get_date(item, "starts_on"), rows.get_date_or_none(item, "ends_on")),
            )
            for item in self.db.query(
                f"SELECT {_CERT} FROM certification WHERE badge = ? ORDER BY body, number",
                [badge],
            )
        )
        return Technician(
            badge=badge,
            name=rows.get_text(row, "name"),
            role=rows.get_enum(row, "role", Role),
            employed=window,
            certifications=certifications,
        )

    def get(self, badge: str) -> Technician:
        wanted = badge_number(badge)
        row = self.db.query_one(f"SELECT {_PERSON} FROM technician WHERE badge = ?", [wanted])
        if row is None:
            raise NotFoundError("no such badge", badge=wanted)
        return self._person(row)

    def exists(self, badge: str) -> bool:
        wanted = badge_number(badge)
        return self.db.scalar("SELECT 1 FROM technician WHERE badge = ?", [wanted]) is not None

    def roster(self) -> Roster:
        found = self.db.query(f"SELECT {_PERSON} FROM technician ORDER BY badge")
        return Roster.of(self._person(row) for row in found)

    def save_competency(self, entry: Competency) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO competency ({_COMPETENCY}) VALUES (?, ?, ?, ?, ?, ?)",
            [
                entry.badge,
                entry.task.value,
                rows.put_date(entry.assessed_on),
                entry.assessor,
                entry.observations,
                rows.put_date(entry.valid_until),
            ],
        )

    def _competency(self, row: sqlite3.Row) -> Competency:
        return Competency(
            badge=rows.get_text(row, "badge"),
            task=rows.get_enum(row, "task", Task),
            assessed_on=rows.get_date(row, "assessed_on"),
            assessor=rows.get_text(row, "assessor"),
            observations=rows.get_int(row, "observations"),
            valid_until=rows.get_date_or_none(row, "valid_until"),
        )

    def competencies(self, badge: str | None = None) -> CompetencyFile:
        if badge is None:
            found = self.db.query(f"SELECT {_COMPETENCY} FROM competency ORDER BY badge, task")
        else:
            found = self.db.query(
                f"SELECT {_COMPETENCY} FROM competency WHERE badge = ? ORDER BY task",
                [badge_number(badge)],
            )
        return CompetencyFile.of(self._competency(row) for row in found)

    def may_release(self, badge: str, day: date) -> str | None:
        """Why this badge may not sign a release today, or None."""
        person = self.get(badge)
        refusal = person.refusal_to_release(day)
        if refusal is not None:
            return refusal
        return self.competencies(badge).refusal(badge, Task.RELEASE, day)
