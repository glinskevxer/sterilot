"""Reading a probe trace out of a file.

Both kinds of chamber can be made to dump a trace: a column of offsets and a
column of temperatures. It is the only input in the department that gives an
honest lethality figure, and it is also the only one that arrives with the
first three lines being the machine's idea of a header.

Offsets may be seconds from the start or clock times. Both are read, and a file
mixing the two is rejected rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sterilot.clock import parse_moment
from sterilot.errors import ValidationError
from sterilot.ingest.source import RowProblem, read_delimited
from sterilot.trace import Trace
from sterilot.units.temperature import Temperature

REQUIRED = ("offset", "temperature")

ALIASES = {
    "seconds": "offset",
    "elapsed": "offset",
    "elapsed_s": "offset",
    "time": "offset",
    "timestamp": "offset",
    "temp": "temperature",
    "temp_c": "temperature",
    "chamber_c": "temperature",
    "probe": "temperature",
}


@dataclass(frozen=True)
class TraceImport:
    """What came out of one trace file."""

    trace: Trace | None
    problems: tuple[RowProblem, ...] = ()

    @property
    def clean(self) -> bool:
        return self.trace is not None and not self.problems

    def summary(self) -> str:
        if self.trace is None:
            return f"no trace read, {len(self.problems)} rows rejected"
        return (
            f"{len(self.trace)} samples over {self.trace.duration.spelled()},"
            f" {len(self.problems)} rows rejected"
        )


def load_trace(text: str, started_at: datetime | None = None) -> TraceImport:
    """Read a trace file into a :class:`Trace`."""
    result = read_delimited(text, required=REQUIRED, aliases=ALIASES)
    problems = list(result.problems)
    pairs: list[tuple[float, float]] = []
    stamps: list[datetime] = []
    for row in result.rows:
        raw = row.require("offset")
        try:
            celsius = Temperature.parse(row.require("temperature")).celsius
        except ValidationError as exc:
            problems.append(RowProblem(row.number, "has no readable temperature", exc.message))
            continue
        if _looks_like_a_clock(raw):
            try:
                stamps.append(parse_moment(raw))
            except ValidationError as exc:
                problems.append(RowProblem(row.number, "has no readable time", exc.message))
                continue
            pairs.append((0.0, celsius))
        else:
            try:
                pairs.append((float(raw), celsius))
            except ValueError:
                problems.append(RowProblem(row.number, "has no readable offset", raw))
    if stamps and len(stamps) != len(pairs):
        raise ValidationError("the file mixes clock times and offsets")
    if stamps:
        first = stamps[0]
        pairs = [
            ((stamp - first).total_seconds(), celsius)
            for stamp, (_, celsius) in zip(stamps, pairs, strict=True)
        ]
        started_at = started_at or first
    if len(pairs) < 2:
        return TraceImport(None, tuple(problems))
    trace = Trace.from_pairs(started_at or datetime.now().replace(microsecond=0), pairs)
    return TraceImport(trace, tuple(problems))


def _looks_like_a_clock(value: str) -> bool:
    return ":" in value or "-" in value or "/" in value
