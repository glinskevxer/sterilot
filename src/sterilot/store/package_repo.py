"""Reading and writing sterile storage.

Locations, par levels and the packages on the shelves. The events on a package
are append only for the same reason tray events are: what happened to a pack is
not something the next write should be able to forget.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sterilot.errors import NotFoundError
from sterilot.ids import LotControlNumber, asset_tag, normalise_code, tray_code
from sterilot.settings import Settings
from sterilot.storage.event import Event, EventRecord, Package, Packaging
from sterilot.storage.pick import PickResult, ShelfItem, on_hand, pick
from sterilot.storage.shelf import Location, ParLevel, StorageMap, Zone
from sterilot.store import rows
from sterilot.store.db import Database

_LOCATION = (
    "code, description, zone, capacity_units, floor_cm, sprinkler_cm, wall_cm,"
    " closed_shelving, under_plumbing"
)
_PACKAGE = "asset, lot, packaging, sterilized_at, location"


@dataclass
class PackageStore:
    """Sterile storage."""

    db: Database

    def save_location(self, location: Location) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO location ({_LOCATION}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                location.code,
                location.description,
                location.zone.value,
                location.capacity_units,
                location.floor_clearance_cm,
                location.sprinkler_clearance_cm,
                location.outside_wall_clearance_cm,
                rows.put_bool(location.closed_shelving),
                rows.put_bool(location.under_plumbing),
            ],
        )

    def _location(self, row: sqlite3.Row) -> Location:
        return Location(
            code=rows.get_text(row, "code"),
            description=rows.get_text(row, "description"),
            zone=rows.get_enum(row, "zone", Zone),
            capacity_units=rows.get_int(row, "capacity_units"),
            floor_clearance_cm=float(row["floor_cm"]),
            sprinkler_clearance_cm=float(row["sprinkler_cm"]),
            outside_wall_clearance_cm=float(row["wall_cm"]),
            closed_shelving=rows.get_bool(row, "closed_shelving"),
            under_plumbing=rows.get_bool(row, "under_plumbing"),
        )

    def location(self, code: str) -> Location:
        wanted = normalise_code(code, field="location code")
        row = self.db.query_one(f"SELECT {_LOCATION} FROM location WHERE code = ?", [wanted])
        if row is None:
            raise NotFoundError("no such location", code=wanted)
        return self._location(row)

    def save_par(self, par: ParLevel) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO par_level (code, minimum, target) VALUES (?, ?, ?)",
            [par.code, par.minimum, par.target],
        )

    def storage_map(self) -> StorageMap:
        locations = tuple(
            self._location(row)
            for row in self.db.query(f"SELECT {_LOCATION} FROM location ORDER BY code")
        )
        pars = tuple(
            ParLevel(
                rows.get_text(row, "code"),
                rows.get_int(row, "minimum"),
                rows.get_int(row, "target"),
            )
            for row in self.db.query("SELECT code, minimum, target FROM par_level ORDER BY code")
        )
        return StorageMap(locations, pars)

    def shelve(self, package: Package, location: str, code: str) -> None:
        """Put a package on a shelf, keeping every event it carries."""
        with self.db.transaction():
            self.db.execute(
                f"INSERT OR REPLACE INTO package ({_PACKAGE}) VALUES (?, ?, ?, ?, ?)",
                [
                    package.asset,
                    package.lot.format(),
                    package.packaging.value,
                    rows.put_moment(package.sterilized_at),
                    normalise_code(location, field="location code"),
                ],
            )
            self.db.execute_many(
                "INSERT OR REPLACE INTO package_event (asset, lot, at, event, by_badge, note)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    [
                        package.asset,
                        package.lot.format(),
                        rows.put_moment(record.at),
                        record.event.value,
                        record.by,
                        record.note,
                    ]
                    for record in package.events
                ],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO tray (asset, code, ownership, owner)"
                " VALUES (?, ?, coalesce((SELECT ownership FROM tray WHERE asset = ?),"
                " 'department'), coalesce((SELECT owner FROM tray WHERE asset = ?), ''))",
                [package.asset, tray_code(code), package.asset, package.asset],
            )

    def record_event(self, asset: str, lot: LotControlNumber, record: EventRecord) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO package_event (asset, lot, at, event, by_badge, note)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                asset_tag(asset),
                lot.format(),
                rows.put_moment(record.at),
                record.event.value,
                record.by,
                record.note,
            ],
        )

    def _package(self, row: sqlite3.Row) -> Package:
        asset = rows.get_text(row, "asset")
        lot = LotControlNumber.parse(rows.get_text(row, "lot"))
        events = tuple(
            EventRecord(
                rows.get_enum(item, "event", Event),
                rows.get_moment(item, "at"),
                rows.get_text(item, "by_badge"),
                rows.get_text_or_empty(item, "note"),
            )
            for item in self.db.query(
                "SELECT at, event, by_badge, note FROM package_event"
                " WHERE asset = ? AND lot = ? ORDER BY at",
                [asset, lot.format()],
            )
        )
        return Package(
            asset=asset,
            lot=lot,
            packaging=rows.get_enum(row, "packaging", Packaging),
            sterilized_at=rows.get_moment(row, "sterilized_at"),
            events=events,
        )

    def package(self, asset: str, lot: LotControlNumber) -> Package:
        row = self.db.query_one(
            f"SELECT {_PACKAGE} FROM package WHERE asset = ? AND lot = ?",
            [asset_tag(asset), lot.format()],
        )
        if row is None:
            raise NotFoundError("no package with that tag and lot", asset=asset_tag(asset))
        return self._package(row)

    def shelf(self) -> tuple[ShelfItem, ...]:
        found = self.db.query(
            f"SELECT p.{_PACKAGE.replace(', ', ', p.')}, t.code AS code FROM package p"
            " JOIN tray t ON t.asset = p.asset ORDER BY p.sterilized_at, p.asset"
        )
        return tuple(
            ShelfItem(
                self._package(row), rows.get_text(row, "code"), rows.get_text(row, "location")
            )
            for row in found
        )

    def on_hand(self, now: datetime, settings: Settings | None = None) -> dict[str, int]:
        return on_hand(self.shelf(), now, settings)

    def pick(
        self, code: str, quantity: int, now: datetime, settings: Settings | None = None
    ) -> PickResult:
        return pick(self.shelf(), code, quantity, now, settings)

    def remove(self, items: Iterable[ShelfItem]) -> None:
        with self.db.transaction():
            for item in items:
                self.db.execute(
                    "DELETE FROM package_event WHERE asset = ? AND lot = ?",
                    [item.asset, item.package.lot.format()],
                )
                self.db.execute(
                    "DELETE FROM package WHERE asset = ? AND lot = ?",
                    [item.asset, item.package.lot.format()],
                )
