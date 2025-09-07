"""The compliance report, which covers a period rather than a day.

This is the one that gets pulled before an accreditation visit, and the reason
it exists is that the answer to "were the daily tests done" is not a number
anybody can produce from a shelf of paper in an afternoon.

Everything in it is a count of days a machine ran against days it was tested,
loads against what was decided about them, and exceptions against whether they
were closed inside their own response time. No opinions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sterilot.load.record import LoadStatus
from sterilot.quality.log import duties_for_sterilizer, duties_for_washer
from sterilot.quality.nonconformance import Severity
from sterilot.reporting import coverage
from sterilot.reporting.render import Column, heading, join, pairs, section, table
from sterilot.settings import Settings
from sterilot.store.store import Store


@dataclass(frozen=True)
class MachineCoverage:
    """One machine over the period."""

    equipment: str
    kind: str
    days_run: int
    days_covered: int

    @property
    def gaps(self) -> int:
        return self.days_run - self.days_covered

    @property
    def rate(self) -> float:
        return 1.0 if self.days_run == 0 else self.days_covered / self.days_run

    def describe(self) -> str:
        return f"{self.equipment} {self.days_covered} of {self.days_run} days covered"


@dataclass(frozen=True)
class ComplianceReport:
    """A period, counted."""

    start: date
    end: date
    facility: str
    machines: tuple[MachineCoverage, ...]
    loads: dict[LoadStatus, int]
    exceptions: dict[Severity, int]
    overdue_exceptions: int
    storage_problems: tuple[str, ...]
    lapsed_competencies: tuple[str, ...]

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    @property
    def total_loads(self) -> int:
        return sum(self.loads.values())

    @property
    def coverage(self) -> float:
        run = sum(item.days_run for item in self.machines)
        covered = sum(item.days_covered for item in self.machines)
        return 1.0 if run == 0 else covered / run

    @property
    def clean(self) -> bool:
        return not (
            any(item.gaps for item in self.machines)
            or self.overdue_exceptions
            or self.storage_problems
            or self.lapsed_competencies
            or self.loads.get(LoadStatus.RECALLED, 0)
        )

    def render(self) -> str:
        return join(
            [
                heading(
                    f"{self.facility} compliance {self.start.isoformat()} to {self.end.isoformat()}"
                ),
                pairs(
                    [
                        ("days", self.days),
                        ("loads", self.total_loads),
                        ("daily test coverage", f"{self.coverage * 100:.1f} percent"),
                        ("overdue exceptions", self.overdue_exceptions),
                        ("verdict", "clean" if self.clean else "see below"),
                    ]
                ),
                section("Machines", self._machines()),
                section("Loads", self._loads()),
                section("Exceptions", self._exceptions()),
                section("Storage", "\n".join(self.storage_problems)),
                section("Competency", "\n".join(self.lapsed_competencies)),
            ]
        )

    def _machines(self) -> str:
        if not self.machines:
            return ""
        return table(
            [
                Column("machine"),
                Column("kind"),
                Column("days run", align="right"),
                Column("covered", align="right"),
                Column("gaps", align="right"),
            ],
            [
                [item.equipment, item.kind, item.days_run, item.days_covered, item.gaps]
                for item in self.machines
            ],
        )

    def _loads(self) -> str:
        if not self.total_loads:
            return ""
        return table(
            [Column("status"), Column("loads", align="right")],
            [
                [status.label, count]
                for status, count in sorted(self.loads.items(), key=lambda row: row[0].value)
            ],
        )

    def _exceptions(self) -> str:
        if not self.exceptions:
            return ""
        return table(
            [Column("severity"), Column("raised", align="right")],
            [
                [severity.label, count]
                for severity, count in sorted(
                    self.exceptions.items(), key=lambda row: row[0].response_days
                )
            ],
        )

    def __str__(self) -> str:
        return self.render()


def build(
    store: Store, start: date, end: date, settings: Settings | None = None
) -> ComplianceReport:
    """Count a period. ``end`` is exclusive, the way every window here is."""
    rules = settings or Settings()
    days = _days(start, end)
    machines: list[MachineCoverage] = []
    for unit in store.equipment.sterilizers():
        duties = duties_for_sterilizer(unit)
        machines.append(
            MachineCoverage(
                unit.equipment,
                "sterilizer",
                coverage.days_run(store, unit.equipment, "sterilizer", days),
                coverage.days_covered(store, unit.equipment, "sterilizer", duties, days),
            )
        )
    for washer in store.equipment.washers():
        duties = duties_for_washer(washer)
        if not duties:
            continue
        machines.append(
            MachineCoverage(
                washer.equipment,
                "washer",
                coverage.days_run(store, washer.equipment, "washer", days),
                coverage.days_covered(store, washer.equipment, "washer", duties, days),
            )
        )

    loads: dict[LoadStatus, int] = {}
    for record in store.loads.on_days(start, end):
        loads[record.status] = loads.get(record.status, 0) + 1

    severities: dict[Severity, int] = {}
    overdue = 0
    for entry in store.quality.exceptions_between(start, end):
        severities[entry.severity] = severities.get(entry.severity, 0) + 1
        if entry.overdue(end):
            overdue += 1

    storage = tuple(
        f"{place.label()}: {problem}"
        for place in store.packages.storage_map().unusable()
        for problem in place.problems()
    )
    lapsed = tuple(
        f"{person.badge} {person.name}: {refusal}"
        for person in store.staff.roster().people
        if (refusal := store.staff.may_release(person.badge, end)) is not None
        and person.role.may_release
    )
    return ComplianceReport(
        start=start,
        end=end,
        facility=rules.facility,
        machines=tuple(machines),
        loads=loads,
        exceptions=severities,
        overdue_exceptions=overdue,
        storage_problems=storage,
        lapsed_competencies=lapsed,
    )


def _days(start: date, end: date) -> tuple[date, ...]:
    span = (end - start).days
    return tuple(start + timedelta(days=offset) for offset in range(max(span, 0)))
