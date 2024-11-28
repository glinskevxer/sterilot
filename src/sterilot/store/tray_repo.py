"""Reading and writing physical trays.

A tray is a row plus its history, and the history is append only. Saving a tray
writes the events it does not already have rather than replacing the run,
because two benches can move two different trays at the same moment and neither
should be able to lose the other's work.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.assets.lifecycle import Stage, TrayEvent
from sterilot.assets.tray import Ownership, TrayInstance
from sterilot.errors import NotFoundError
from sterilot.ids import asset_tag, tray_code
from sterilot.store import rows
from sterilot.store.db import Database


@dataclass
class TrayStore:
    """Trays and the events that moved them."""

    db: Database

    def save(self, tray: TrayInstance) -> None:
        with self.db.transaction():
            self.db.execute(
                "INSERT OR REPLACE INTO tray (asset, code, ownership, owner, retired_on)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    tray.asset,
                    tray.code,
                    tray.ownership.value,
                    tray.owner,
                    rows.put_date(tray.retired_on),
                ],
            )
            self.db.execute_many(
                "INSERT OR IGNORE INTO tray_event (asset, at, stage, by_badge, note)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    [tray.asset, rows.put_moment(event.at), event.stage.value, event.by, event.note]
                    for event in tray.history
                ],
            )

    def get(self, asset: str) -> TrayInstance:
        wanted = asset_tag(asset)
        row = self.db.query_one(
            "SELECT asset, code, ownership, owner, retired_on FROM tray WHERE asset = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("no tray with that asset tag", asset=wanted)
        return self._build(row)

    def _build(self, row: sqlite3.Row) -> TrayInstance:
        asset = rows.get_text(row, "asset")
        history = tuple(
            TrayEvent(
                rows.get_moment(event, "at"),
                rows.get_enum(event, "stage", Stage),
                rows.get_text(event, "by_badge"),
                rows.get_text_or_empty(event, "note"),
            )
            for event in self.db.query(
                "SELECT at, stage, by_badge, note FROM tray_event WHERE asset = ? ORDER BY at",
                [asset],
            )
        )
        return TrayInstance(
            asset=asset,
            code=rows.get_text(row, "code"),
            ownership=rows.get_enum(row, "ownership", Ownership),
            owner=rows.get_text_or_empty(row, "owner"),
            history=history,
            retired_on=rows.get_date_or_none(row, "retired_on"),
        )

    def exists(self, asset: str) -> bool:
        wanted = asset_tag(asset)
        return self.db.scalar("SELECT 1 FROM tray WHERE asset = ?", [wanted]) is not None

    def of_code(self, code: str) -> tuple[TrayInstance, ...]:
        wanted = tray_code(code)
        found = self.db.query(
            "SELECT asset, code, ownership, owner, retired_on FROM tray WHERE code = ?"
            " ORDER BY asset",
            [wanted],
        )
        return tuple(self._build(row) for row in found)

    def in_stage(self, stage: Stage) -> tuple[TrayInstance, ...]:
        """Trays whose most recent event puts them in ``stage``."""
        found = self.db.query(
            "SELECT t.asset, t.code, t.ownership, t.owner, t.retired_on FROM tray t"
            " JOIN tray_event e ON e.asset = t.asset"
            " WHERE e.at = (SELECT max(at) FROM tray_event WHERE asset = t.asset)"
            "   AND e.stage = ?"
            " ORDER BY t.asset",
            [stage.value],
        )
        return tuple(self._build(row) for row in found)

    def retired(self, on_or_before: date | None = None) -> tuple[TrayInstance, ...]:
        if on_or_before is None:
            found = self.db.query(
                "SELECT asset, code, ownership, owner, retired_on FROM tray"
                " WHERE retired_on IS NOT NULL ORDER BY asset"
            )
        else:
            found = self.db.query(
                "SELECT asset, code, ownership, owner, retired_on FROM tray"
                " WHERE retired_on IS NOT NULL AND retired_on <= ? ORDER BY asset",
                [rows.put_date(on_or_before)],
            )
        return tuple(self._build(row) for row in found)

    def counts_by_stage(self) -> dict[Stage, int]:
        found = self.db.query(
            "SELECT e.stage AS stage, count(*) AS total FROM tray t"
            " JOIN tray_event e ON e.asset = t.asset"
            " WHERE e.at = (SELECT max(at) FROM tray_event WHERE asset = t.asset)"
            " GROUP BY e.stage"
        )
        return {rows.get_enum(row, "stage", Stage): rows.get_int(row, "total") for row in found}
