"""Turning the washer export into cycle records.

The washer writes one line per phase, so a cycle arrives as four or five rows
that have to be gathered back together by machine, day and cycle number. Rows
that will not parse are reported rather than dropped, and a cycle whose program
name is not one the department has defined is reported too: the numbers may
well be fine and nobody can say so without the program.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sterilot.clock import parse_moment
from sterilot.decon.cycle import Phase, PhaseRecord, Program, WasherCycle
from sterilot.errors import ValidationError
from sterilot.ingest.source import Row, RowProblem, read_delimited
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

REQUIRED = ("machine", "cycle", "program", "started", "operator", "phase", "seconds")

ALIASES = {
    "washer": "machine",
    "unit": "machine",
    "cycle_no": "cycle",
    "cycle_number": "cycle",
    "program_name": "program",
    "start": "started",
    "start_time": "started",
    "started_at": "started",
    "user": "operator",
    "step": "phase",
    "duration_s": "seconds",
    "duration": "seconds",
    "peak_c": "peak",
    "peak_temp": "peak",
}


@dataclass(frozen=True)
class WasherImport:
    """What came out of one export file."""

    cycles: tuple[WasherCycle, ...] = ()
    problems: tuple[RowProblem, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        return f"{len(self.cycles)} cycles read, {len(self.problems)} rows rejected"


def _key(row: Row) -> tuple[str, str, str]:
    return row.require("machine"), row.require("cycle"), row.require("started")


def _phase_record(row: Row) -> PhaseRecord:
    phase = Phase.named(row.require("phase"))
    ran_for = Duration.parse(row.require("seconds"), bare_unit="s")
    peak = Temperature.parse(row.get("peak")) if row.has("peak") else None
    return PhaseRecord(phase, ran_for, peak)


def load_washer_cycles(text: str, programs: Mapping[str, Program]) -> WasherImport:
    """Read an export into washer cycles, using the programs the department has."""
    result = read_delimited(text, required=REQUIRED, aliases=ALIASES)
    problems = list(result.problems)
    grouped: dict[tuple[str, str, str], list[Row]] = {}
    order: list[tuple[str, str, str]] = []
    for row in result.rows:
        try:
            key = _key(row)
        except ValidationError as exc:
            problems.append(RowProblem(row.number, "is missing a key field", exc.message))
            continue
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)

    cycles: list[WasherCycle] = []
    for key in order:
        rows = grouped[key]
        first = rows[0]
        name = first.require("program").strip().upper().replace(" ", "-")
        program = programs.get(name)
        if program is None:
            problems.append(RowProblem(first.number, "names a program we do not have", name))
            continue
        try:
            started = parse_moment(first.require("started"))
            number = int(first.require("cycle"))
            records = tuple(_phase_record(row) for row in rows)
            cycles.append(
                WasherCycle(
                    equipment=first.require("machine"),
                    program=program,
                    number=number,
                    started_at=started,
                    operator=first.require("operator"),
                    phases=records,
                )
            )
        except (ValidationError, ValueError) as exc:
            problems.append(RowProblem(first.number, "will not build a cycle", str(exc)))
    return WasherImport(tuple(cycles), tuple(problems))


def latest_start(cycles: tuple[WasherCycle, ...]) -> datetime | None:
    """The most recent cycle in a run, which is where the next read starts."""
    if not cycles:
        return None
    return max(cycle.started_at for cycle in cycles)
