"""The daily report, which is what gets printed and initialled.

One page a day: what ran, what was released, what is still held, what tests are
missing and what went wrong. An inspector who reads a year of these should be
able to see the department working without opening the database.

The report is built from the store rather than passed the records, because the
whole point is that nobody assembles it by hand at half past six.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.quality.nonconformance import Nonconformance
from sterilot.reporting import coverage
from sterilot.reporting.render import Column, bullets, heading, join, pairs, section, table
from sterilot.settings import Settings
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.store.store import Store


@dataclass(frozen=True)
class DutyGap:
    """A test a machine owed and did not get."""

    equipment: str
    duty: str

    def describe(self) -> str:
        return f"{self.equipment} has no {self.duty} test"


@dataclass(frozen=True)
class DailyReport:
    """One day, assembled."""

    day: date
    facility: str
    cycles: tuple[SterilizerCycle, ...]
    loads: tuple[LoadRecord, ...]
    gaps: tuple[DutyGap, ...]
    exceptions: tuple[Nonconformance, ...]
    trays_out: int

    @property
    def released(self) -> tuple[LoadRecord, ...]:
        return tuple(record for record in self.loads if record.released)

    @property
    def held(self) -> tuple[LoadRecord, ...]:
        return tuple(record for record in self.loads if record.status is LoadStatus.HELD)

    @property
    def rejected(self) -> tuple[LoadRecord, ...]:
        return tuple(record for record in self.loads if record.status is LoadStatus.REJECTED)

    @property
    def clean(self) -> bool:
        """Nothing missing, nothing rejected and nothing raised."""
        return not (self.gaps or self.rejected or self.exceptions)

    def render(self) -> str:
        return join(
            [
                heading(f"{self.facility} daily report {self.day.isoformat()}"),
                pairs(
                    [
                        ("cycles", len(self.cycles)),
                        ("loads", len(self.loads)),
                        ("released", len(self.released)),
                        ("held", len(self.held)),
                        ("rejected", len(self.rejected)),
                        ("trays out", self.trays_out),
                        ("verdict", "clean" if self.clean else "see below"),
                    ]
                ),
                section("Cycles", self._cycles()),
                section("Loads", self._loads()),
                section("Missing tests", bullets(gap.describe() for gap in self.gaps)),
                section("Exceptions", self._exceptions()),
            ]
        )

    def _cycles(self) -> str:
        if not self.cycles:
            return ""
        return table(
            [
                Column("lot"),
                Column("started"),
                Column("method"),
                Column("hold"),
                Column("exposure"),
                Column("aborted"),
            ],
            [
                [
                    cycle.lot.format(),
                    cycle.started_at.strftime("%H:%M"),
                    cycle.method.value,
                    cycle.measurements.hold_temperature.format(),
                    cycle.measurements.exposure.spelled(),
                    cycle.abort_reason or "",
                ]
                for cycle in self.cycles
            ],
        )

    def _loads(self) -> str:
        if not self.loads:
            return ""
        return table(
            [Column("reference"), Column("lot"), Column("status"), Column("why")],
            [
                [
                    record.reference,
                    record.lot.format(),
                    record.status.label,
                    "; ".join(record.decision.reasons) if record.decision else "",
                ]
                for record in self.loads
            ],
        )

    def _exceptions(self) -> str:
        if not self.exceptions:
            return ""
        return table(
            [Column("reference"), Column("severity"), Column("subject"), Column("what")],
            [
                [entry.reference, entry.severity.label, entry.subject, entry.description]
                for entry in self.exceptions
            ],
        )

    def __str__(self) -> str:
        return self.render()


def build(store: Store, day: date, settings: Settings | None = None) -> DailyReport:
    """Assemble the day's report from the store."""
    rules = settings or Settings()
    cycles: list[SterilizerCycle] = []
    for unit in store.equipment.sterilizers():
        cycles.extend(store.cycles.on_day(unit.equipment, day))
    gaps = tuple(DutyGap(gap.equipment, gap.duty.label) for gap in coverage.owed(store, day))

    tomorrow = date.fromordinal(day.toordinal() + 1)
    loads = store.loads.on_days(day, tomorrow)
    exceptions = store.quality.exceptions_between(day, tomorrow)
    return DailyReport(
        day=day,
        facility=rules.facility,
        cycles=tuple(sorted(cycles, key=lambda item: (item.equipment, item.run))),
        loads=loads,
        gaps=gaps,
        exceptions=exceptions,
        trays_out=len(store.issues.open_issues()),
    )
