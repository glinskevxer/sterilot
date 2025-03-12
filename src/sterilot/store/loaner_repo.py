"""Reading and writing vendor loaner sets."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.assets.loaner import LoanerSet, LoanerStage
from sterilot.errors import NotFoundError
from sterilot.ids import case_number, normalise_code
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = (
    "reference, vendor, set_name, case_number, case_start, expected_at, received_at, counted_at,"
    " reprocessed_at, released_at, decontaminated_at, returned_at, piece_count, rep_present"
)


@dataclass
class LoanerStore:
    """Somebody else's instruments, while they are here."""

    db: Database

    def save(self, loaner: LoanerSet) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO loaner ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                loaner.reference,
                loaner.vendor,
                loaner.set_name,
                loaner.case,
                rows.put_moment(loaner.case_start),
                rows.put_moment(loaner.expected_at),
                rows.put_moment(loaner.received_at),
                rows.put_moment(loaner.counted_at),
                rows.put_moment(loaner.reprocessed_at),
                rows.put_moment(loaner.released_at),
                rows.put_moment(loaner.decontaminated_at),
                rows.put_moment(loaner.returned_at),
                loaner.piece_count,
                rows.put_bool(loaner.rep_present_at_count),
            ],
        )

    def _build(self, row: sqlite3.Row) -> LoanerSet:
        return LoanerSet(
            reference=rows.get_text(row, "reference"),
            vendor=rows.get_text(row, "vendor"),
            set_name=rows.get_text(row, "set_name"),
            case=rows.get_text(row, "case_number"),
            case_start=rows.get_moment(row, "case_start"),
            expected_at=rows.get_moment(row, "expected_at"),
            received_at=rows.get_moment_or_none(row, "received_at"),
            counted_at=rows.get_moment_or_none(row, "counted_at"),
            reprocessed_at=rows.get_moment_or_none(row, "reprocessed_at"),
            released_at=rows.get_moment_or_none(row, "released_at"),
            decontaminated_at=rows.get_moment_or_none(row, "decontaminated_at"),
            returned_at=rows.get_moment_or_none(row, "returned_at"),
            piece_count=rows.get_int_or_none(row, "piece_count"),
            rep_present_at_count=rows.get_bool(row, "rep_present"),
        )

    def get(self, reference: str) -> LoanerSet:
        wanted = normalise_code(reference, field="loaner reference")
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM loaner WHERE reference = ?", [wanted])
        if row is None:
            raise NotFoundError("no loaner with that reference", reference=wanted)
        return self._build(row)

    def exists(self, reference: str) -> bool:
        wanted = normalise_code(reference, field="loaner reference")
        return self.db.scalar("SELECT 1 FROM loaner WHERE reference = ?", [wanted]) is not None

    def for_case(self, case: str) -> tuple[LoanerSet, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM loaner WHERE case_number = ? ORDER BY reference",
            [case_number(case)],
        )
        return tuple(self._build(row) for row in found)

    def expected_on(self, day: date) -> tuple[LoanerSet, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM loaner WHERE case_start >= ? AND case_start < ?"
            " ORDER BY case_start",
            [f"{day.isoformat()}T00:00:00", f"{day.isoformat()}T23:59:59"],
        )
        return tuple(self._build(row) for row in found)

    def outstanding(self) -> tuple[LoanerSet, ...]:
        """Everything still here, in whatever state."""
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM loaner WHERE returned_at IS NULL ORDER BY case_start"
        )
        return tuple(self._build(row) for row in found)

    def not_ready(
        self, day: date, lead_hours: int
    ) -> tuple[tuple[LoanerSet, tuple[str, ...]], ...]:
        """Loaners for a day's cases that are not fit to go out yet."""
        found: list[tuple[LoanerSet, tuple[str, ...]]] = []
        for loaner in self.expected_on(day):
            if loaner.stage is LoanerStage.RETURNED:
                continue
            problems = loaner.problems(lead_hours)
            if problems:
                found.append((loaner, problems))
        return tuple(found)
