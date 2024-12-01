"""Reading and writing sterilizer cycles.

A cycle is stored by its lot control number, which is the only identifier that
appears on the labels, so the label is enough to find the record.

The cycle specification is not stored with the run. A spec is a department
standard that applies to every cycle of that name, and copying it onto ten
thousand rows would mean a corrected tolerance never reaching the old ones. The
store takes a resolver instead, and the department decides what a name means.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sterilot.errors import NotFoundError
from sterilot.ids import LotControlNumber, equipment_id
from sterilot.methods import Method
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.store import rows
from sterilot.store.db import Database
from sterilot.units.pressure import Pressure

SpecResolver = Callable[[str, Method], CycleSpec]

_COLUMNS = (
    "lot, equipment_id, run_date, run, cycle_name, method, started_at, operator,"
    " hold_c, exposure_s, dry_s, pressure_kpa, pulses, aborted, abort_reason"
)


def standard_spec(name: str, method: Method) -> CycleSpec:
    """The default resolver: the department's own cycle for the method."""
    spec = CycleSpec.standard(method)
    if spec.name == name:
        return spec
    return CycleSpec(
        name,
        spec.method,
        spec.temperature,
        spec.exposure,
        spec.dry_time,
        spec.superheat_limit,
        spec.conditioning_pulses,
    )


@dataclass
class CycleStore:
    """Sterilizer cycles, keyed by lot control number."""

    db: Database
    resolve_spec: SpecResolver = field(default=standard_spec)

    def register_equipment(self, equipment: str, kind: str, model: str, manufacturer: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO equipment (equipment_id, kind, model, manufacturer)"
            " VALUES (?, ?, ?, ?)",
            [equipment_id(equipment), kind, model, manufacturer],
        )

    def save(self, cycle: SterilizerCycle) -> None:
        measured = cycle.measurements
        self.db.execute(
            f"INSERT OR REPLACE INTO sterilizer_cycle ({_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                cycle.lot.format(),
                cycle.equipment,
                rows.put_date(cycle.day),
                cycle.run,
                cycle.spec.name,
                cycle.method.value,
                rows.put_moment(cycle.started_at),
                cycle.operator,
                rows.put_celsius(measured.hold_temperature),
                rows.put_seconds(measured.exposure),
                rows.put_seconds(measured.dry_time),
                None
                if measured.chamber_pressure is None
                else measured.chamber_pressure.kilopascals,
                measured.conditioning_pulses,
                rows.put_bool(cycle.aborted),
                cycle.abort_reason,
            ],
        )

    def get(self, lot: LotControlNumber | str) -> SterilizerCycle:
        key = (
            lot.format()
            if isinstance(lot, LotControlNumber)
            else LotControlNumber.parse(lot).format()
        )
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM sterilizer_cycle WHERE lot = ?", [key])
        if row is None:
            raise NotFoundError("no cycle with that lot control number", lot=key)
        return self._build(row)

    def _build(self, row: sqlite3.Row) -> SterilizerCycle:
        method = rows.get_enum(row, "method", Method)
        pressure = row["pressure_kpa"]
        measured = CycleMeasurements(
            hold_temperature=rows.get_temperature(row, "hold_c"),
            exposure=rows.get_duration(row, "exposure_s"),
            dry_time=rows.get_duration_or_zero(row, "dry_s"),
            chamber_pressure=None if pressure is None else Pressure(float(pressure)),
            conditioning_pulses=rows.get_int_or_none(row, "pulses"),
        )
        return SterilizerCycle(
            lot=LotControlNumber.parse(rows.get_text(row, "lot")),
            spec=self.resolve_spec(rows.get_text(row, "cycle_name"), method),
            started_at=rows.get_moment(row, "started_at"),
            operator=rows.get_text(row, "operator"),
            measurements=measured,
            aborted=rows.get_bool(row, "aborted"),
            abort_reason=rows.get_text_or_empty(row, "abort_reason"),
        )

    def exists(self, lot: LotControlNumber) -> bool:
        return (
            self.db.scalar("SELECT 1 FROM sterilizer_cycle WHERE lot = ?", [lot.format()])
            is not None
        )

    def on_day(self, equipment: str, day: date) -> tuple[SterilizerCycle, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM sterilizer_cycle WHERE equipment_id = ? AND run_date = ?"
            " ORDER BY run",
            [equipment_id(equipment), rows.put_date(day)],
        )
        return tuple(self._build(row) for row in found)

    def next_run(self, equipment: str, day: date) -> int:
        found = self.db.scalar(
            "SELECT max(run) FROM sterilizer_cycle WHERE equipment_id = ? AND run_date = ?",
            [equipment_id(equipment), rows.put_date(day)],
        )
        return 1 if found is None else int(found) + 1

    def between(self, equipment: str, start: date, end: date) -> tuple[SterilizerCycle, ...]:
        found = self.db.query(
            f"SELECT {_COLUMNS} FROM sterilizer_cycle"
            " WHERE equipment_id = ? AND run_date >= ? AND run_date < ?"
            " ORDER BY run_date, run",
            [equipment_id(equipment), rows.put_date(start), rows.put_date(end)],
        )
        return tuple(self._build(row) for row in found)

    def aborted(self, equipment: str | None = None) -> tuple[SterilizerCycle, ...]:
        if equipment is None:
            found = self.db.query(
                f"SELECT {_COLUMNS} FROM sterilizer_cycle WHERE aborted = 1 ORDER BY started_at"
            )
        else:
            found = self.db.query(
                f"SELECT {_COLUMNS} FROM sterilizer_cycle WHERE aborted = 1 AND equipment_id = ?"
                " ORDER BY started_at",
                [equipment_id(equipment)],
            )
        return tuple(self._build(row) for row in found)
