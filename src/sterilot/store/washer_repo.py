"""Reading and writing wash programs and the cycles run against them.

Programs are stored because they are department definitions that change, and a
cycle read back has to be judged against the program as it is now. That is the
opposite of the sterilizer specification, which is resolved rather than stored,
and the difference is deliberate: a wash program is edited by the department
and a sterilizer cycle is a standard.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.decon.cycle import Phase, PhaseRecord, PhaseSpec, Program, WasherCycle
from sterilot.decon.washer import WasherClass
from sterilot.errors import NotFoundError
from sterilot.ids import equipment_id, normalise_code
from sterilot.store import rows
from sterilot.store.db import Database
from sterilot.tolerance import Band
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

_CYCLE = "equipment_id, number, started_at, program, operator, aborted"
_PHASE = "equipment_id, started_at, number, phase, seconds, peak_c"


@dataclass
class WasherStore:
    """Wash programs and wash cycles."""

    db: Database

    def save_program(self, program: Program) -> None:
        with self.db.transaction():
            self.db.execute(
                "INSERT OR REPLACE INTO wash_program (name, washer_class, a0_floor)"
                " VALUES (?, ?, ?)",
                [program.name, program.washer_class.value, program.a0_floor],
            )
            self.db.execute("DELETE FROM wash_program_phase WHERE name = ?", [program.name])
            self.db.execute_many(
                "INSERT INTO wash_program_phase (name, phase, minimum_s, low_c, high_c, detergent)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    [
                        program.name,
                        spec.phase.value,
                        spec.minimum.seconds,
                        None if spec.temperature is None else spec.temperature.low,
                        None if spec.temperature is None else spec.temperature.high,
                        spec.detergent,
                    ]
                    for spec in program.phases
                ],
            )

    def program(self, name: str) -> Program:
        wanted = normalise_code(name, field="program name")
        row = self.db.query_one(
            "SELECT name, washer_class, a0_floor FROM wash_program WHERE name = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("no wash program with that name", name=wanted)
        phases = self.db.query(
            "SELECT phase, minimum_s, low_c, high_c, detergent FROM wash_program_phase"
            " WHERE name = ? ORDER BY rowid",
            [wanted],
        )
        return Program.of(
            wanted,
            [self._spec(item) for item in phases],
            washer_class=WasherClass.named(rows.get_text(row, "washer_class")),
            a0_floor=None if row["a0_floor"] is None else float(row["a0_floor"]),
        )

    def _spec(self, row: sqlite3.Row) -> PhaseSpec:
        low = row["low_c"]
        high = row["high_c"]
        band = None
        if low is not None or high is not None:
            band = Band(
                None if low is None else float(low),
                None if high is None else float(high),
                rows.get_text(row, "phase"),
            )
        return PhaseSpec(
            phase=rows.get_enum(row, "phase", Phase),
            minimum=rows.get_duration(row, "minimum_s"),
            temperature=band,
            detergent=rows.get_text_or_empty(row, "detergent"),
        )

    def programs(self) -> dict[str, Program]:
        found = self.db.query("SELECT name FROM wash_program ORDER BY name")
        return {str(row["name"]): self.program(str(row["name"])) for row in found}

    def save_cycle(self, cycle: WasherCycle) -> None:
        with self.db.transaction():
            self.db.execute(
                f"INSERT OR REPLACE INTO washer_cycle ({_CYCLE}) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    cycle.equipment,
                    cycle.number,
                    rows.put_moment(cycle.started_at),
                    cycle.program.name,
                    cycle.operator,
                    rows.put_bool(cycle.aborted),
                ],
            )
            self.db.execute_many(
                f"INSERT OR REPLACE INTO washer_phase ({_PHASE}) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    [
                        cycle.equipment,
                        rows.put_moment(cycle.started_at),
                        cycle.number,
                        record.phase.value,
                        record.ran_for.seconds,
                        None if record.peak is None else record.peak.celsius,
                    ]
                    for record in cycle.phases
                ],
            )

    def _cycle(self, row: sqlite3.Row) -> WasherCycle:
        equipment = rows.get_text(row, "equipment_id")
        started = rows.get_moment(row, "started_at")
        number = rows.get_int(row, "number")
        phases = tuple(
            PhaseRecord(
                rows.get_enum(item, "phase", Phase),
                rows.get_duration(item, "seconds"),
                None if item["peak_c"] is None else Temperature(float(item["peak_c"])),
            )
            for item in self.db.query(
                "SELECT phase, seconds, peak_c FROM washer_phase"
                " WHERE equipment_id = ? AND started_at = ? AND number = ? ORDER BY rowid",
                [equipment, rows.put_moment(started), number],
            )
        )
        return WasherCycle(
            equipment=equipment,
            program=self.program(rows.get_text(row, "program")),
            number=number,
            started_at=started,
            operator=rows.get_text(row, "operator"),
            phases=phases,
            aborted=rows.get_bool(row, "aborted"),
        )

    def cycle(self, equipment: str, started_at: datetime, number: int) -> WasherCycle:
        row = self.db.query_one(
            f"SELECT {_CYCLE} FROM washer_cycle"
            " WHERE equipment_id = ? AND started_at = ? AND number = ?",
            [equipment_id(equipment), rows.put_moment(started_at), number],
        )
        if row is None:
            raise NotFoundError("no wash cycle there", equipment=equipment_id(equipment))
        return self._cycle(row)

    def on_day(self, equipment: str, day: date) -> tuple[WasherCycle, ...]:
        found = self.db.query(
            f"SELECT {_CYCLE} FROM washer_cycle WHERE equipment_id = ?"
            " AND started_at >= ? AND started_at < ? ORDER BY started_at, number",
            [
                equipment_id(equipment),
                f"{day.isoformat()}T00:00:00",
                f"{day.isoformat()}T23:59:59",
            ],
        )
        return tuple(self._cycle(row) for row in found)

    def standard_program(self) -> Program:
        """The department's instrument program, created on first use."""
        try:
            return self.program("INSTRUMENT-1")
        except NotFoundError:
            program = Program.of(
                "instrument 1",
                [
                    PhaseSpec(Phase.PREWASH, Duration.of_minutes(2), Band.at_most(45.0, "prewash")),
                    PhaseSpec(
                        Phase.WASH, Duration.of_minutes(5), Band.at_least(55.0, "wash"), "enzymatic"
                    ),
                    PhaseSpec(Phase.RINSE, Duration.of_minutes(1)),
                    PhaseSpec(
                        Phase.THERMAL, Duration.of_minutes(5), Band.at_least(90.0, "thermal")
                    ),
                    PhaseSpec(Phase.DRY, Duration.of_minutes(10)),
                ],
            )
            self.save_program(program)
            return program
