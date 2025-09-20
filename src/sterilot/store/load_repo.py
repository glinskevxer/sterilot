"""Reading and writing load records.

A load is a header, its items, and whatever has been decided about it. All
three live in the same write, because a load half saved is a load nobody can
account for.

Finding a load by tray is the query this table exists for. It is what a recall
runs, and it is why load_item carries an index on the asset tag rather than
being read through the header.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.errors import NotFoundError
from sterilot.ids import LotControlNumber, asset_tag, equipment_id, normalise_code
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.store import rows
from sterilot.store.cycle_repo import CycleStore
from sterilot.store.db import Database
from sterilot.units.mass import Mass

_HEADER = (
    "reference, lot, method, built_by, built_at, status, decided_at, decided_by, kind,"
    " reasons, recalled_at, recall_note"
)


@dataclass
class LoadStore:
    """Load records, read back through the cycle store."""

    db: Database
    cycles: CycleStore

    def save(self, record: LoadRecord) -> None:
        load = record.load
        decision = record.decision
        with self.db.transaction():
            self.db.execute(
                f"INSERT OR REPLACE INTO load_record ({_HEADER})"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    load.reference,
                    record.lot.format(),
                    load.method.value,
                    load.built_by,
                    rows.put_moment(load.built_at),
                    record.status.value,
                    None if decision is None else rows.put_moment(decision.at),
                    None if decision is None else decision.by,
                    None if decision is None else decision.kind.value,
                    rows.put_list(() if decision is None else decision.reasons),
                    rows.put_moment(record.recalled_at),
                    record.recall_reason,
                ],
            )
            self.db.execute("DELETE FROM load_item WHERE reference = ?", [load.reference])
            self.db.execute_many(
                "INSERT INTO load_item (reference, asset, code, units, weight_g, implant,"
                " textile, shelf) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        load.reference,
                        item.asset,
                        item.code,
                        item.units,
                        rows.put_grams(item.weight),
                        rows.put_bool(item.implant),
                        rows.put_bool(item.textile),
                        item.shelf,
                    ]
                    for item in load.items
                ],
            )

    def get(self, reference: str) -> LoadRecord:
        wanted = normalise_code(reference, field="load reference")
        row = self.db.query_one(f"SELECT {_HEADER} FROM load_record WHERE reference = ?", [wanted])
        if row is None:
            raise NotFoundError("no load with that reference", load=wanted)
        return self._build(row)

    def _build(self, row: sqlite3.Row) -> LoadRecord:
        reference = rows.get_text(row, "reference")
        items = tuple(
            LoadItem(
                asset=rows.get_text(item, "asset"),
                code=rows.get_text(item, "code"),
                units=rows.get_int(item, "units"),
                weight=rows.get_mass_or_none(item, "weight_g"),
                implant=rows.get_bool(item, "implant"),
                textile=rows.get_bool(item, "textile"),
                shelf=rows.get_int(item, "shelf"),
            )
            for item in self.db.query(
                "SELECT asset, code, units, weight_g, implant, textile, shelf FROM load_item"
                " WHERE reference = ? ORDER BY asset",
                [reference],
            )
        )
        load = Load(
            reference=reference,
            method=rows.get_enum(row, "method", Method),
            items=items,
            built_by=rows.get_text(row, "built_by"),
            built_at=rows.get_moment(row, "built_at"),
        )
        cycle = self.cycles.get(LotControlNumber.parse(rows.get_text(row, "lot")))
        decision = self._decision(row)
        return LoadRecord(
            load=load,
            cycle=cycle,
            decision=decision,
            recalled_at=rows.get_moment_or_none(row, "recalled_at"),
            recall_reason=rows.get_text_or_empty(row, "recall_note"),
        )

    def _decision(self, row: sqlite3.Row) -> ReleaseDecision | None:
        if row["kind"] is None:
            return None
        return ReleaseDecision(
            kind=rows.get_enum(row, "kind", ReleaseKind),
            reasons=rows.get_list(row, "reasons"),
            at=rows.get_moment(row, "decided_at"),
            by=rows.get_text(row, "decided_by"),
        )

    def exists(self, reference: str) -> bool:
        wanted = normalise_code(reference, field="load reference")
        return self.db.scalar("SELECT 1 FROM load_record WHERE reference = ?", [wanted]) is not None

    def for_asset(self, asset: str) -> tuple[LoadRecord, ...]:
        found = self.db.query(
            f"SELECT {_HEADER} FROM load_record WHERE reference IN"
            " (SELECT reference FROM load_item WHERE asset = ?) ORDER BY built_at",
            [asset_tag(asset)],
        )
        return tuple(self._build(row) for row in found)

    def for_lot(self, lot: LotControlNumber) -> tuple[LoadRecord, ...]:
        found = self.db.query(
            f"SELECT {_HEADER} FROM load_record WHERE lot = ? ORDER BY reference", [lot.format()]
        )
        return tuple(self._build(row) for row in found)

    def with_status(self, status: LoadStatus) -> tuple[LoadRecord, ...]:
        found = self.db.query(
            f"SELECT {_HEADER} FROM load_record WHERE status = ? ORDER BY built_at",
            [status.value],
        )
        return tuple(self._build(row) for row in found)

    def between(self, start: datetime, end: datetime) -> tuple[LoadRecord, ...]:
        found = self.db.query(
            f"SELECT {_HEADER} FROM load_record WHERE built_at >= ? AND built_at < ?"
            " ORDER BY built_at",
            [rows.put_moment(start), rows.put_moment(end)],
        )
        return tuple(self._build(row) for row in found)

    def on_days(self, start: date, end: date) -> tuple[LoadRecord, ...]:
        """Loads whose cycle ran in ``[start, end)``.

        The day a load belongs to is the day its chamber ran, not the moment
        somebody typed the load in. A night shift load built at ten past
        midnight belongs to the cycle that carried it.
        """
        found = self.db.query(
            f"SELECT l.{_HEADER.replace(', ', ', l.')} FROM load_record l"
            " JOIN sterilizer_cycle c ON c.lot = l.lot"
            " WHERE c.run_date >= ? AND c.run_date < ? ORDER BY c.run_date, c.run",
            [rows.put_date(start), rows.put_date(end)],
        )
        return tuple(self._build(row) for row in found)

    def on_equipment(self, equipment: str, day: date | None = None) -> tuple[LoadRecord, ...]:
        if day is None:
            found = self.db.query(
                f"SELECT l.{_HEADER.replace(', ', ', l.')} FROM load_record l"
                " JOIN sterilizer_cycle c ON c.lot = l.lot WHERE c.equipment_id = ?"
                " ORDER BY c.run_date, c.run",
                [equipment_id(equipment)],
            )
        else:
            found = self.db.query(
                f"SELECT l.{_HEADER.replace(', ', ', l.')} FROM load_record l"
                " JOIN sterilizer_cycle c ON c.lot = l.lot"
                " WHERE c.equipment_id = ? AND c.run_date = ? ORDER BY c.run",
                [equipment_id(equipment), rows.put_date(day)],
            )
        return tuple(self._build(row) for row in found)

    def total_weight(self, reference: str) -> Mass:
        return self.get(reference).load.known_weight()
