"""Reading and writing what happened before the washer.

Point of use treatment and the sink are the two records the department is most
often asked for and least often keeps, because they happen furthest from a
keyboard. Holding them here means a cleaning failure can be traced back to the
trip the set had rather than stopping at the washer that was blamed for it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.decon.manual import ManualClean, PointOfUse
from sterilot.errors import NotFoundError
from sterilot.ids import case_number, catalog_number
from sterilot.store import rows
from sterilot.store.db import Database
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

_TRIP = "case_number, finished_at, collected_at, kept_moist, closed, soil_removed"
_CLEAN = (
    "catalog, cleaned_at, by_badge, soaked_s, detergent_c, brush_mm, brush_passes,"
    " disassembled, case_number"
)


@dataclass
class DeconStore:
    """The room and the sink."""

    db: Database

    def save_trip(self, trip: PointOfUse) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO point_of_use ({_TRIP}) VALUES (?, ?, ?, ?, ?, ?)",
            [
                trip.case,
                rows.put_moment(trip.finished_at),
                rows.put_moment(trip.collected_at),
                rows.put_bool(trip.kept_moist),
                rows.put_bool(trip.container_closed),
                rows.put_bool(trip.gross_soil_removed),
            ],
        )

    def _trip(self, row: sqlite3.Row) -> PointOfUse:
        return PointOfUse(
            case=rows.get_text(row, "case_number"),
            finished_at=rows.get_moment(row, "finished_at"),
            collected_at=rows.get_moment(row, "collected_at"),
            kept_moist=rows.get_bool(row, "kept_moist"),
            container_closed=rows.get_bool(row, "closed"),
            gross_soil_removed=rows.get_bool(row, "soil_removed"),
        )

    def trip(self, case: str) -> PointOfUse:
        row = self.db.query_one(
            f"SELECT {_TRIP} FROM point_of_use WHERE case_number = ? ORDER BY finished_at DESC"
            " LIMIT 1",
            [case_number(case)],
        )
        if row is None:
            raise NotFoundError("no point of use record for that case", case=case_number(case))
        return self._trip(row)

    def trips_on(self, day: date) -> tuple[PointOfUse, ...]:
        start, end = rows.day_window(day)
        found = self.db.query(
            f"SELECT {_TRIP} FROM point_of_use WHERE finished_at >= ? AND finished_at < ?"
            " ORDER BY finished_at",
            [start, end],
        )
        return tuple(self._trip(row) for row in found)

    def delayed_trips(self, day: date) -> tuple[PointOfUse, ...]:
        return tuple(trip for trip in self.trips_on(day) if trip.problems())

    def save_clean(self, record: ManualClean, case: str = "") -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO manual_clean ({_CLEAN}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.catalog,
                rows.put_moment(record.at),
                record.by,
                record.soaked.seconds,
                record.detergent_temperature.celsius,
                record.brush_mm,
                record.brush_passes,
                rows.put_bool(record.disassembled),
                case_number(case) if case else "",
            ],
        )

    def _clean(self, row: sqlite3.Row) -> ManualClean:
        brush = row["brush_mm"]
        return ManualClean(
            catalog=rows.get_text(row, "catalog"),
            at=rows.get_moment(row, "cleaned_at"),
            by=rows.get_text(row, "by_badge"),
            soaked=Duration(float(row["soaked_s"])),
            detergent_temperature=Temperature(float(row["detergent_c"])),
            brush_mm=None if brush is None else float(brush),
            brush_passes=rows.get_int(row, "brush_passes"),
            disassembled=rows.get_bool(row, "disassembled"),
        )

    def clean(self, catalog: str, at: datetime) -> ManualClean:
        row = self.db.query_one(
            f"SELECT {_CLEAN} FROM manual_clean WHERE catalog = ? AND cleaned_at = ?",
            [catalog_number(catalog), rows.put_moment(at)],
        )
        if row is None:
            raise NotFoundError("no sink record there", catalog=catalog_number(catalog))
        return self._clean(row)

    def cleans_for_case(self, case: str) -> tuple[ManualClean, ...]:
        found = self.db.query(
            f"SELECT {_CLEAN} FROM manual_clean WHERE case_number = ? ORDER BY cleaned_at",
            [case_number(case)],
        )
        return tuple(self._clean(row) for row in found)

    def cleans_of(self, catalog: str) -> tuple[ManualClean, ...]:
        found = self.db.query(
            f"SELECT {_CLEAN} FROM manual_clean WHERE catalog = ? ORDER BY cleaned_at",
            [catalog_number(catalog)],
        )
        return tuple(self._clean(row) for row in found)
