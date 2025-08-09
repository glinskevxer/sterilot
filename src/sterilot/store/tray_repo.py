"""Reading and writing physical trays.

A tray is a row plus its history, and the history is append only. Saving a tray
writes the events it does not already have rather than replacing the run,
because two benches can move two different trays at the same moment and neither
should be able to lose the other's work.

Events are numbered rather than keyed on the moment they happened. Timestamps
are whole seconds and a tray can reach the same stage twice inside one, which
with a natural key silently dropped the second one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.assets.lifecycle import Stage, TrayEvent
from sterilot.assets.tray import Ownership, TrayInstance
from sterilot.errors import NotFoundError
from sterilot.ids import asset_tag, tray_code
from sterilot.quality.metrics import Turnaround
from sterilot.store import rows
from sterilot.store.db import Database

_LATEST_EVENT = "SELECT rowid FROM tray_event WHERE asset = t.asset ORDER BY seq DESC LIMIT 1"


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
                "INSERT OR REPLACE INTO tray_event (asset, seq, at, stage, by_badge, note)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    [
                        tray.asset,
                        number,
                        rows.put_moment(event.at),
                        event.stage.value,
                        event.by,
                        event.note,
                    ]
                    for number, event in enumerate(tray.history, start=1)
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
                "SELECT at, stage, by_badge, note FROM tray_event WHERE asset = ? ORDER BY seq",
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
        """Trays whose most recent event puts them in ``stage``.

        Two moves can land in the same second, so the latest event is the one
        with the highest sequence number rather than the highest timestamp.
        """
        found = self.db.query(
            "SELECT t.asset, t.code, t.ownership, t.owner, t.retired_on FROM tray t"
            f" JOIN tray_event e ON e.rowid = ({_LATEST_EVENT})"
            " WHERE e.stage = ?"
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

    def turnarounds(self, start: date, end: date) -> tuple[Turnaround, ...]:
        """Every completed trip round the loop that finished in the window.

        A trip is a soiled event and the next sterile event after it. A tray
        that went round twice in the window gives two, and one still in the
        middle of a trip gives none.
        """
        found: list[Turnaround] = []
        first, last = rows.day_window(start)[0], rows.day_window(end)[0]
        for row in self.db.query("SELECT asset FROM tray ORDER BY asset"):
            asset = str(row["asset"])
            soiled: datetime | None = None
            for event in self.db.query(
                "SELECT at, stage FROM tray_event WHERE asset = ? ORDER BY seq", [asset]
            ):
                stage = rows.get_enum(event, "stage", Stage)
                moment = rows.get_moment(event, "at")
                if stage is Stage.SOILED:
                    soiled = moment
                elif stage is Stage.STERILE and soiled is not None:
                    stamp = moment.isoformat(timespec="seconds")
                    if first <= stamp < last:
                        found.append(Turnaround(asset, soiled, moment))
                    soiled = None
        return tuple(found)

    def counts_by_stage(self) -> dict[Stage, int]:
        found = self.db.query(
            "SELECT e.stage AS stage, count(*) AS total FROM tray t"
            f" JOIN tray_event e ON e.rowid = ({_LATEST_EVENT})"
            " GROUP BY e.stage"
        )
        return {rows.get_enum(row, "stage", Stage): rows.get_int(row, "total") for row in found}
