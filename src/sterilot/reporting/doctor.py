"""Everything the department is behind on, in one place.

Each of these questions already has an answer somewhere in the code. What
nobody has is the list, and a supervisor coming back from two weeks off should
be able to get it in one command rather than remembering to ask eight.

Findings carry a severity so the list sorts itself. Nothing here writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from sterilot.load.record import LoadStatus
from sterilot.reporting.render import Column, heading, join, table
from sterilot.settings import Settings
from sterilot.store.store import Store


class Level(Enum):
    """How much attention a finding wants."""

    STOP = "stop"
    SOON = "soon"
    NOTE = "note"

    @property
    def rank(self) -> int:
        return list(Level).index(self)

    @property
    def label(self) -> str:
        return self.value


@dataclass(frozen=True)
class Finding:
    """One thing the department is behind on."""

    level: Level
    area: str
    subject: str
    detail: str

    def describe(self) -> str:
        return f"[{self.level.label}] {self.area} {self.subject}: {self.detail}"


@dataclass(frozen=True)
class Report:
    """Everything found, worst first."""

    day: date
    findings: tuple[Finding, ...]

    @property
    def clear(self) -> bool:
        return not self.findings

    @property
    def stops(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.level is Level.STOP)

    def render(self) -> str:
        if self.clear:
            return heading(f"Department check {self.day.isoformat()}") + "\nnothing outstanding"
        return join(
            [
                heading(f"Department check {self.day.isoformat()}"),
                table(
                    [Column("level"), Column("area"), Column("subject"), Column("detail")],
                    [
                        [item.level.label, item.area, item.subject, item.detail]
                        for item in self.findings
                    ],
                ),
            ]
        )

    def __str__(self) -> str:
        return self.render()


def check(store: Store, day: date, settings: Settings | None = None) -> Report:
    """Ask every question at once."""
    rules = settings or Settings()
    found: list[Finding] = []

    for unit in store.equipment.sterilizers():
        refusal = unit.refusal_on(day)
        if refusal is not None:
            found.append(Finding(Level.STOP, "sterilizer", unit.equipment, refusal))
    for washer in store.equipment.washers():
        refusal = washer.refusal_on(day)
        if refusal is not None:
            found.append(Finding(Level.STOP, "washer", washer.equipment, refusal))

    for record in store.loads.with_status(LoadStatus.HELD):
        detail = "; ".join(record.decision.reasons) if record.decision else "held"
        found.append(Finding(Level.SOON, "load", record.reference, detail))

    for entry in store.quality.open_exceptions():
        if entry.overdue(day):
            found.append(
                Finding(Level.STOP, "exception", entry.reference, f"response due {entry.due_on()}")
            )
        else:
            found.append(Finding(Level.NOTE, "exception", entry.reference, f"due {entry.due_on()}"))

    for container in store.containers.due_for_inspection(day):
        found.append(Finding(Level.SOON, "container", container.asset, "due for inspection"))

    for lot, expires in store.indicators.expiring(day, 60):
        level = Level.STOP if expires <= day else Level.SOON
        found.append(Finding(level, "indicator", lot, f"expires {expires.isoformat()}"))

    for place in store.packages.storage_map().unusable():
        for problem in place.problems():
            found.append(Finding(Level.STOP, "storage", place.code, problem))

    for person in store.staff.roster().on_duty(day):
        if not person.role.may_release:
            continue
        refusal = store.staff.may_release(person.badge, day)
        if refusal is not None:
            found.append(Finding(Level.SOON, "staff", person.badge, refusal))

    for loaner, problems in store.loaners.not_ready(day, rules.loaner_lead_hours):
        found.append(Finding(Level.SOON, "loaner", loaner.reference, "; ".join(problems)))

    for order in store.repairs.overdue(day):
        days = order.days_out(day)
        found.append(
            Finding(Level.NOTE, "repair", order.reference, f"{days} days at {order.vendor}")
        )

    found.sort(key=lambda item: (item.level.rank, item.area, item.subject))
    return Report(day, tuple(found))
