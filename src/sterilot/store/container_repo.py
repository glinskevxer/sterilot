"""Reading and writing rigid containers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from sterilot.assets.container import Container, FilterType
from sterilot.errors import NotFoundError
from sterilot.ids import asset_tag
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.store import rows
from sterilot.store.db import Database

_COLUMNS = (
    "asset, model, manufacturer, filter_type, filter_positions, starts_on, ends_on,"
    " last_inspection, cycles_since, gasket_intact, latches_intact"
)


@dataclass
class ContainerStore:
    """Containers and how far they are from their next inspection."""

    db: Database

    def save(self, container: Container) -> None:
        window = container.in_service
        self.db.execute(
            f"INSERT OR REPLACE INTO container ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                container.asset,
                container.model,
                container.manufacturer,
                container.filter_type.value,
                container.filter_positions,
                rows.put_date(None if window is None else window.start),
                rows.put_date(None if window is None else window.end),
                rows.put_date(container.last_inspection),
                container.cycles_since_inspection,
                rows.put_bool(container.gasket_intact),
                rows.put_bool(container.latches_intact),
            ],
        )

    def _build(self, row: sqlite3.Row) -> Container:
        starts = rows.get_date_or_none(row, "starts_on")
        ends = rows.get_date_or_none(row, "ends_on")
        window = None
        if starts is not None or ends is not None:
            window = DateRange(starts or date(1970, 1, 1), ends)
        return Container(
            asset=rows.get_text(row, "asset"),
            model=rows.get_text(row, "model"),
            manufacturer=rows.get_text(row, "manufacturer"),
            filter_type=rows.get_enum(row, "filter_type", FilterType),
            filter_positions=rows.get_int(row, "filter_positions"),
            in_service=window,
            last_inspection=rows.get_date_or_none(row, "last_inspection"),
            cycles_since_inspection=rows.get_int(row, "cycles_since"),
            gasket_intact=rows.get_bool(row, "gasket_intact"),
            latches_intact=rows.get_bool(row, "latches_intact"),
        )

    def get(self, asset: str) -> Container:
        wanted = asset_tag(asset)
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM container WHERE asset = ?", [wanted])
        if row is None:
            raise NotFoundError("no container with that asset tag", asset=wanted)
        return self._build(row)

    def exists(self, asset: str) -> bool:
        wanted = asset_tag(asset)
        return self.db.scalar("SELECT 1 FROM container WHERE asset = ?", [wanted]) is not None

    def all(self) -> tuple[Container, ...]:
        found = self.db.query(f"SELECT {_COLUMNS} FROM container ORDER BY asset")
        return tuple(self._build(row) for row in found)

    def used(self, asset: str) -> Container:
        """Record one cycle against a container and save it."""
        container = self.get(asset).after_cycle()
        self.save(container)
        return container

    def inspected(
        self, asset: str, day: date, gasket_intact: bool = True, latches_intact: bool = True
    ) -> Container:
        container = self.get(asset).inspected(day, gasket_intact, latches_intact)
        self.save(container)
        return container

    def due_for_inspection(self, day: date) -> tuple[Container, ...]:
        return tuple(item for item in self.all() if item.inspection_due(day))

    def usable_for(self, method: Method, day: date) -> tuple[Container, ...]:
        return tuple(item for item in self.all() if item.usable_for(method, day))

    def filters_needed(self, day: date) -> int:
        """Filters the department burns if every usable container runs once."""
        return sum(
            item.filters_per_cycle for item in self.all() if item.refusal_on_any_method(day) is None
        )
