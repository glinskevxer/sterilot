"""A machine trace: what the chamber probe read, and when.

Both the washers and the sterilizers can be made to dump a trace rather than
just the summary line their printers produce. A trace is worth having because
the summary is a claim and the trace is the evidence, and because lethality is
an integral over the trace and cannot be recovered from a peak and a time.

Offsets are seconds from the start of the cycle, which is what the machines
export. The wall clock start is carried alongside so a point can be placed on
the department clock when a report needs it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sterilot.errors import ValidationError
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


@dataclass(frozen=True)
class TracePoint:
    """One sample. ``offset`` is seconds from the start of the cycle."""

    offset: float
    temperature: Temperature

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValidationError(
                "a sample cannot sit before the cycle started", offset=self.offset
            )

    def moment(self, started_at: datetime) -> datetime:
        return started_at + timedelta(seconds=self.offset)


@dataclass(frozen=True)
class Trace:
    """A run of samples in offset order."""

    started_at: datetime
    points: tuple[TracePoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValidationError("a trace needs at least two samples", count=len(self.points))
        for earlier, later in zip(self.points, self.points[1:], strict=False):
            if later.offset <= earlier.offset:
                raise ValidationError(
                    "trace samples must step forward",
                    offset=later.offset,
                    previous=earlier.offset,
                )

    @classmethod
    def from_pairs(cls, started_at: datetime, pairs: Iterable[tuple[float, float]]) -> Trace:
        """Build from ``(offset seconds, celsius)`` pairs."""
        points = tuple(TracePoint(offset, Temperature(celsius)) for offset, celsius in pairs)
        return cls(started_at, points)

    @classmethod
    def flat(cls, started_at: datetime, celsius: float, seconds: float, step: float = 1.0) -> Trace:
        """A synthetic square trace, which is what a spec sheet describes."""
        if seconds <= 0:
            raise ValidationError("a flat trace needs a length", seconds=seconds)
        offsets: list[float] = []
        offset = 0.0
        while offset < seconds:
            offsets.append(offset)
            offset += step
        offsets.append(seconds)
        return cls.from_pairs(started_at, ((value, celsius) for value in offsets))

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self) -> Iterator[TracePoint]:
        return iter(self.points)

    @property
    def duration(self) -> Duration:
        return Duration(self.points[-1].offset - self.points[0].offset)

    @property
    def finished_at(self) -> datetime:
        return self.points[-1].moment(self.started_at)

    def peak(self) -> Temperature:
        return max(point.temperature for point in self.points)

    def trough(self) -> Temperature:
        return min(point.temperature for point in self.points)

    def at(self, offset: float) -> Temperature:
        """The reading at ``offset``, interpolated between samples."""
        first, last = self.points[0], self.points[-1]
        if offset < first.offset or offset > last.offset:
            raise ValidationError("offset is outside the trace", offset=offset)
        for earlier, later in zip(self.points, self.points[1:], strict=False):
            if earlier.offset <= offset <= later.offset:
                span = later.offset - earlier.offset
                if span == 0:
                    return earlier.temperature
                weight = (offset - earlier.offset) / span
                rise = later.temperature.difference(earlier.temperature)
                return earlier.temperature.offset_by(rise * weight)
        return last.temperature

    def time_above(self, threshold: Temperature) -> Duration:
        """How long the trace spent at or above ``threshold``.

        Crossings are interpolated, so a probe sampling every thirty seconds
        does not cost the cycle half a minute of credit at each end.
        """
        seconds = 0.0
        for earlier, later in zip(self.points, self.points[1:], strict=False):
            span = later.offset - earlier.offset
            low = earlier.temperature.celsius
            high = later.temperature.celsius
            floor = threshold.celsius
            if low >= floor and high >= floor:
                seconds += span
            elif low < floor and high < floor:
                continue
            elif high > low:
                seconds += span * (high - floor) / (high - low)
            else:
                seconds += span * (low - floor) / (low - high)
        return Duration(seconds)

    def integrate(self, weight: Callable[[Temperature], float]) -> float:
        """Trapezoid integral of ``weight`` over the trace, in second units."""
        total = 0.0
        for earlier, later in zip(self.points, self.points[1:], strict=False):
            span = later.offset - earlier.offset
            total += span * (weight(earlier.temperature) + weight(later.temperature)) / 2.0
        return total

    def window(self, start: float, end: float) -> Trace:
        """The part of the trace between two offsets, ends interpolated in."""
        if end <= start:
            raise ValidationError("window ends before it starts", start=start, end=end)
        kept: list[TracePoint] = [TracePoint(start, self.at(start))]
        kept.extend(point for point in self.points if start < point.offset < end)
        kept.append(TracePoint(end, self.at(end)))
        return Trace(
            self.started_at + timedelta(seconds=start),
            tuple(TracePoint(point.offset - start, point.temperature) for point in kept),
        )

    def celsius_values(self) -> Sequence[float]:
        return [point.temperature.celsius for point in self.points]
