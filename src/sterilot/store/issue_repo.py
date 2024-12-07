"""Reading and writing the issue log.

Small table, heavily read. Every recall, every case query and every "where is
ORT-0114" comes through here, so the asset and the case both carry indexes and
the whereabouts question is answered in one query rather than by loading the
tray's whole history.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sterilot.cases.issue import Disposition, Issue, IssueLog
from sterilot.errors import ConflictError, NotFoundError
from sterilot.ids import asset_tag, case_number
from sterilot.recall.notice import Whereabouts
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = "asset, issued_at, case_number, issued_by, returned_at, disposition"


@dataclass
class IssueStore:
    """Trays out to cases."""

    db: Database

    def save(self, issue: Issue) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO issue ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
            [
                issue.asset,
                rows.put_moment(issue.issued_at),
                issue.case,
                issue.issued_by,
                rows.put_moment(issue.returned_at),
                issue.disposition.value,
            ],
        )

    def save_all(self, issues: Iterable[Issue]) -> None:
        with self.db.transaction():
            for issue in issues:
                self.save(issue)

    def issue_out(self, issue: Issue) -> None:
        """Record a tray going out, refusing one that is already out."""
        if self.open_for(issue.asset) is not None:
            raise ConflictError("that tray is already out", asset=issue.asset)
        self.save(issue)

    def _build(self, row: sqlite3.Row) -> Issue:
        return Issue(
            asset=rows.get_text(row, "asset"),
            case=rows.get_text(row, "case_number"),
            issued_at=rows.get_moment(row, "issued_at"),
            issued_by=rows.get_text(row, "issued_by"),
            returned_at=rows.get_moment_or_none(row, "returned_at"),
            disposition=rows.get_enum(row, "disposition", Disposition),
        )

    def get(self, asset: str, issued_at: datetime) -> Issue:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM issue WHERE asset = ? AND issued_at = ?",
            [asset_tag(asset), rows.put_moment(issued_at)],
        )
        if row is None:
            raise NotFoundError("no issue of that tray at that time", asset=asset_tag(asset))
        return self._build(row)

    def for_asset(self, asset: str) -> tuple[Issue, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM issue WHERE asset = ? ORDER BY issued_at",
            [asset_tag(asset)],
        )
        return tuple(self._build(row) for row in found)

    def for_case(self, case: str) -> tuple[Issue, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM issue WHERE case_number = ? ORDER BY issued_at",
            [case_number(case)],
        )
        return tuple(self._build(row) for row in found)

    def open_for(self, asset: str) -> Issue | None:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM issue WHERE asset = ? AND disposition = ?",
            [asset_tag(asset), Disposition.OPEN.value],
        )
        return None if row is None else self._build(row)

    def open_issues(self) -> tuple[Issue, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM issue WHERE disposition = ? ORDER BY issued_at",
            [Disposition.OPEN.value],
        )
        return tuple(self._build(row) for row in found)

    def latest_for(self, asset: str) -> Issue | None:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM issue WHERE asset = ? ORDER BY issued_at DESC LIMIT 1",
            [asset_tag(asset)],
        )
        return None if row is None else self._build(row)

    def whereabouts(self, asset: str) -> tuple[Whereabouts, str]:
        latest = self.latest_for(asset)
        if latest is None:
            return Whereabouts.UNKNOWN, ""
        return latest.whereabouts, latest.case

    def locations(self, assets: Iterable[str]) -> dict[str, tuple[Whereabouts, str]]:
        return {asset_tag(asset): self.whereabouts(asset) for asset in assets}

    def log(self) -> IssueLog:
        found = self.db.query(f"SELECT {_COLUMNS} FROM issue ORDER BY issued_at")
        return IssueLog.of(self._build(row) for row in found)
