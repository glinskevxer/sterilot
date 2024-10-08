"""Department metrics, kept honest.

Three numbers get quoted at every meeting and all three are easy to flatter.
Turnaround gets quoted as an average, which hides the tray that took two days.
Throughput gets quoted in trays, which makes a day of small sets look like a
good day. First pass yield gets quoted without saying what counts as a pass.

So the summary carries a median and a ninetieth percentile alongside the mean,
throughput counts chamber units as well as trays, and yield is defined against
one thing: a load released routinely with no hold and no rework.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sterilot.errors import ValidationError
from sterilot.ids import asset_tag
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.load.release import ReleaseKind
from sterilot.units.duration import Duration


@dataclass(frozen=True)
class Summary:
    """A run of numbers, described without hiding the tail."""

    count: int
    mean: float
    median: float
    p90: float
    lowest: float
    highest: float

    def describe(self, places: int = 1) -> str:
        return (
            f"n={self.count} mean={self.mean:.{places}f} median={self.median:.{places}f} "
            f"p90={self.p90:.{places}f} worst={self.highest:.{places}f}"
        )


def summarise(values: Iterable[float]) -> Summary:
    """Describe a run of numbers. An empty run is refused, not zeroed."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValidationError("nothing to summarise")
    count = len(ordered)
    mean = sum(ordered) / count
    median = _percentile(ordered, 0.5)
    return Summary(count, mean, median, _percentile(ordered, 0.9), ordered[0], ordered[-1])


def _percentile(ordered: Sequence[float], fraction: float) -> float:
    """Linear interpolation between the two nearest ranks."""
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


@dataclass(frozen=True)
class Turnaround:
    """One tray, from soiled to back on the shelf."""

    asset: str
    soiled_at: datetime
    sterile_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        if self.sterile_at < self.soiled_at:
            raise ValidationError("a tray cannot finish before it starts", asset=self.asset)

    @property
    def elapsed(self) -> Duration:
        return Duration((self.sterile_at - self.soiled_at).total_seconds())


def turnaround_hours(runs: Iterable[Turnaround]) -> Summary:
    return summarise(run.elapsed.hours for run in runs)


@dataclass(frozen=True)
class DayTotals:
    """One day on the floor."""

    day: date
    loads: int
    trays: int
    units: int

    @property
    def trays_per_load(self) -> float:
        return self.trays / self.loads if self.loads else 0.0


def throughput(records: Iterable[LoadRecord]) -> tuple[DayTotals, ...]:
    """Loads, trays and chamber units by day, oldest first."""
    grouped: dict[date, list[LoadRecord]] = {}
    for record in records:
        grouped.setdefault(record.cycle.day, []).append(record)
    return tuple(
        DayTotals(
            day,
            len(found),
            sum(len(record.load.items) for record in found),
            sum(record.load.units for record in found),
        )
        for day, found in sorted(grouped.items())
    )


def first_pass_yield(records: Iterable[LoadRecord]) -> float:
    """Share of loads released routinely, with no hold and no rework."""
    found = list(records)
    if not found:
        raise ValidationError("no loads to measure")
    clean = sum(
        1
        for record in found
        if record.decision is not None and record.decision.kind is ReleaseKind.ROUTINE
    )
    return clean / len(found)


def rework_rate(records: Iterable[LoadRecord]) -> float:
    """Share of loads that were rejected or recalled."""
    found = list(records)
    if not found:
        raise ValidationError("no loads to measure")
    spoiled = sum(
        1 for record in found if record.status in {LoadStatus.REJECTED, LoadStatus.RECALLED}
    )
    return spoiled / len(found)


def held_loads(records: Iterable[LoadRecord]) -> tuple[LoadRecord, ...]:
    return tuple(record for record in records if record.status is LoadStatus.HELD)
