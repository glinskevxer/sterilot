"""Reading and writing the quality records.

Two tables with very different shapes. Exceptions are edited, because an
investigation gets written after the fact and a closure comes later still.
Audit entries are never edited at all, and the store refuses an attempt rather
than trusting everybody to remember.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.errors import ConflictError, NotFoundError
from sterilot.ids import normalise_code
from sterilot.quality.audit import GENESIS, Action, AuditEvent, AuditTrail
from sterilot.quality.nonconformance import (
    Category,
    ExceptionRegister,
    Nonconformance,
    Severity,
)
from sterilot.store import rows
from sterilot.store.db import Database

_EXCEPTION = (
    "reference, category, severity, raised_at, raised_by, description, subject, action,"
    " investigation, closed_at, closed_by"
)
_AUDIT = "sequence, at, by_badge, action, subject_kind, subject, detail, previous"


@dataclass
class QualityStore:
    """Exceptions and the audit trail."""

    db: Database

    def save_exception(self, entry: Nonconformance) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO nonconformance ({_EXCEPTION})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                entry.reference,
                entry.category.value,
                entry.severity.value,
                rows.put_moment(entry.raised_at),
                entry.raised_by,
                entry.description,
                entry.subject,
                entry.immediate_action,
                entry.investigation,
                rows.put_moment(entry.closed_at),
                entry.closed_by,
            ],
        )

    def _exception(self, row: sqlite3.Row) -> Nonconformance:
        return Nonconformance(
            reference=rows.get_text(row, "reference"),
            category=rows.get_enum(row, "category", Category),
            severity=rows.get_enum(row, "severity", Severity),
            raised_at=rows.get_moment(row, "raised_at"),
            raised_by=rows.get_text(row, "raised_by"),
            description=rows.get_text(row, "description"),
            subject=rows.get_text_or_empty(row, "subject"),
            immediate_action=rows.get_text_or_empty(row, "action"),
            investigation=rows.get_text_or_empty(row, "investigation"),
            closed_at=rows.get_moment_or_none(row, "closed_at"),
            closed_by=rows.get_text_or_empty(row, "closed_by"),
        )

    def exception(self, reference: str) -> Nonconformance:
        wanted = normalise_code(reference, field="exception reference")
        row = self.db.query_one(
            f"SELECT {_EXCEPTION} FROM nonconformance WHERE reference = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("no exception with that reference", reference=wanted)
        return self._exception(row)

    def open_exceptions(self) -> tuple[Nonconformance, ...]:
        found = self.db.query(
            f"SELECT {_EXCEPTION} FROM nonconformance WHERE closed_at IS NULL ORDER BY raised_at"
        )
        return tuple(self._exception(row) for row in found)

    def exceptions_about(self, subject: str) -> tuple[Nonconformance, ...]:
        found = self.db.query(
            f"SELECT {_EXCEPTION} FROM nonconformance WHERE subject = ? ORDER BY raised_at",
            [subject.strip().upper()],
        )
        return tuple(self._exception(row) for row in found)

    def exceptions_between(self, start: date, end: date) -> tuple[Nonconformance, ...]:
        found = self.db.query(
            f"SELECT {_EXCEPTION} FROM nonconformance WHERE raised_at >= ? AND raised_at < ?"
            " ORDER BY raised_at",
            list(rows.day_bounds(start, end)),
        )
        return tuple(self._exception(row) for row in found)

    def register(self) -> ExceptionRegister:
        found = self.db.query(f"SELECT {_EXCEPTION} FROM nonconformance ORDER BY raised_at")
        return ExceptionRegister.of(self._exception(row) for row in found)

    def append_audit(self, event: AuditEvent) -> None:
        """Append one entry, refusing anything that does not chain."""
        head = self.audit_head()
        if event.previous != head:
            raise ConflictError(
                "that audit entry does not chain onto the last one",
                expected=head,
                given=event.previous,
            )
        self.db.execute(
            "INSERT INTO audit_event (at, by_badge, action, subject_kind, subject, detail,"
            " previous) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                rows.put_moment(event.at),
                event.by,
                event.action.value,
                event.subject_kind,
                event.subject,
                event.detail,
                event.previous,
            ],
        )

    def record(
        self,
        at: datetime,
        by: str,
        action: Action,
        subject_kind: str,
        subject: str,
        detail: str = "",
    ) -> AuditEvent:
        """Build an entry onto the current head and store it."""
        event = AuditEvent(at, by, action, subject_kind, subject, detail, self.audit_head())
        self.append_audit(event)
        return event

    def audit_head(self) -> str:
        row = self.db.query_one(f"SELECT {_AUDIT} FROM audit_event ORDER BY sequence DESC LIMIT 1")
        if row is None:
            return GENESIS
        return self._audit(row).digest()

    def _audit(self, row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            at=rows.get_moment(row, "at"),
            by=rows.get_text(row, "by_badge"),
            action=rows.get_enum(row, "action", Action),
            subject_kind=rows.get_text(row, "subject_kind"),
            subject=rows.get_text(row, "subject"),
            detail=rows.get_text_or_empty(row, "detail"),
            previous=rows.get_text(row, "previous"),
        )

    def audit_trail(self) -> AuditTrail:
        found = self.db.query(f"SELECT {_AUDIT} FROM audit_event ORDER BY sequence")
        return AuditTrail(tuple(self._audit(row) for row in found))

    def audit_for(self, subject_kind: str, subject: str) -> tuple[AuditEvent, ...]:
        found = self.db.query(
            f"SELECT {_AUDIT} FROM audit_event WHERE subject_kind = ? AND subject = ?"
            " ORDER BY sequence",
            [subject_kind, subject],
        )
        return tuple(self._audit(row) for row in found)
