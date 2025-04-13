"""Reading and writing the theatre list and the preference cards."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.cases.preference_card import CardFile, CardLine, PreferenceCard
from sterilot.cases.schedule import Schedule, ScheduledCase
from sterilot.errors import NotFoundError
from sterilot.ids import case_number, normalise_code
from sterilot.interval import DateRange
from sterilot.store import rows
from sterilot.store.db import Database

_CASE = "case_number, room, surgeon, procedure, starts_at, minutes, card_ref"
_CARD = "reference, revision, surgeon, procedure, starts_on, ends_on, loaner_sets"
_LINE = "reference, revision, code, quantity, essential, note"


@dataclass
class ScheduleStore:
    """Cases and the cards they are picked from."""

    db: Database

    def save_case(self, item: ScheduledCase) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO scheduled_case ({_CASE}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                item.case,
                item.room,
                item.surgeon,
                item.procedure,
                rows.put_moment(item.starts_at),
                item.minutes,
                item.card_reference,
            ],
        )

    def _case(self, row: sqlite3.Row) -> ScheduledCase:
        return ScheduledCase(
            case=rows.get_text(row, "case_number"),
            room=rows.get_text(row, "room"),
            surgeon=rows.get_text(row, "surgeon"),
            procedure=rows.get_text(row, "procedure"),
            starts_at=rows.get_moment(row, "starts_at"),
            minutes=rows.get_int(row, "minutes"),
            card_reference=rows.get_text_or_empty(row, "card_ref"),
        )

    def case(self, number: str) -> ScheduledCase:
        wanted = case_number(number)
        row = self.db.query_one(
            f"SELECT {_CASE} FROM scheduled_case WHERE case_number = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("no case with that number", case=wanted)
        return self._case(row)

    def schedule(self, day: date) -> Schedule:
        start, end = rows.day_window(day)
        found = self.db.query(
            f"SELECT {_CASE} FROM scheduled_case WHERE starts_at >= ? AND starts_at < ?"
            " ORDER BY starts_at, room",
            [start, end],
        )
        return Schedule.of(self._case(row) for row in found)

    def save_card(self, card: PreferenceCard) -> None:
        with self.db.transaction():
            self.db.execute(
                f"INSERT OR REPLACE INTO preference_card ({_CARD}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    card.reference,
                    card.revision,
                    card.surgeon,
                    card.procedure,
                    rows.put_date(card.effective.start),
                    rows.put_date(card.effective.end),
                    rows.put_list(card.loaner_sets),
                ],
            )
            self.db.execute(
                "DELETE FROM preference_card_line WHERE reference = ? AND revision = ?",
                [card.reference, card.revision],
            )
            self.db.execute_many(
                f"INSERT INTO preference_card_line ({_LINE}) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    [
                        card.reference,
                        card.revision,
                        line.code,
                        line.quantity,
                        rows.put_bool(line.essential),
                        line.note,
                    ]
                    for line in card.lines
                ],
            )

    def _card(self, row: sqlite3.Row) -> PreferenceCard:
        reference = rows.get_text(row, "reference")
        revision = rows.get_int(row, "revision")
        lines = tuple(
            CardLine(
                rows.get_text(item, "code"),
                rows.get_int(item, "quantity"),
                rows.get_bool(item, "essential"),
                rows.get_text_or_empty(item, "note"),
            )
            for item in self.db.query(
                f"SELECT {_LINE} FROM preference_card_line WHERE reference = ? AND revision = ?"
                " ORDER BY code",
                [reference, revision],
            )
        )
        return PreferenceCard(
            reference=reference,
            surgeon=rows.get_text(row, "surgeon"),
            procedure=rows.get_text(row, "procedure"),
            lines=lines,
            effective=DateRange(
                rows.get_date(row, "starts_on"), rows.get_date_or_none(row, "ends_on")
            ),
            revision=revision,
            loaner_sets=rows.get_list(row, "loaner_sets"),
        )

    def card(self, reference: str, day: date) -> PreferenceCard:
        wanted = normalise_code(reference, field="card reference")
        found = self.db.query(
            f"SELECT {_CARD} FROM preference_card WHERE reference = ? ORDER BY revision",
            [wanted],
        )
        for row in found:
            card = self._card(row)
            if card.in_force_on(day):
                return card
        raise NotFoundError("no card in force with that reference", reference=wanted)

    def cards(self) -> CardFile:
        found = self.db.query(f"SELECT {_CARD} FROM preference_card ORDER BY reference, revision")
        file = CardFile()
        for row in found:
            file = file.with_card(self._card(row))
        return file

    def revise_card(self, card: PreferenceCard) -> None:
        """Close the current revision and store the next one."""
        with self.db.transaction():
            self.db.execute(
                "UPDATE preference_card SET ends_on = ? WHERE reference = ? AND revision = ?",
                [rows.put_date(card.effective.start), card.reference, card.revision - 1],
            )
            self.save_card(card)
