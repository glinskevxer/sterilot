"""Which machines ran, and whether their daily tests were done.

Three reports needed this and all three worked it out their own way, which is
how the daily report came to say a washer owed a cleaning test on a day it
never ran while the compliance report said it did not.

The rule, once: a machine that did not run that day owes nothing, and a machine
that ran owes every duty its kind carries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sterilot.quality.log import Duty, duties_for_sterilizer, duties_for_washer
from sterilot.store.store import Store


@dataclass(frozen=True)
class Gap:
    """A duty a machine that ran has not had."""

    equipment: str
    kind: str
    duty: Duty

    def describe(self) -> str:
        return f"{self.equipment} has no {self.duty.label} test"


def ran_on(store: Store, equipment: str, kind: str, day: date) -> bool:
    """Whether a machine did any work on a day."""
    if kind == "sterilizer":
        return bool(store.cycles.on_day(equipment, day))
    return bool(store.washers.on_day(equipment, day))


def owed(store: Store, day: date) -> tuple[Gap, ...]:
    """Every duty outstanding on every machine that ran, in machine order."""
    found: list[Gap] = []
    for unit in store.equipment.sterilizers():
        found.extend(_gaps(store, unit.equipment, "sterilizer", duties_for_sterilizer(unit), day))
    for washer in store.equipment.washers():
        found.extend(_gaps(store, washer.equipment, "washer", duties_for_washer(washer), day))
    return tuple(found)


def _gaps(store: Store, equipment: str, kind: str, duties: frozenset[Duty], day: date) -> list[Gap]:
    if not duties or not ran_on(store, equipment, kind, day):
        return []
    logged = {entry.duty for entry in store.duties.on_day(equipment, day) if entry.passed}
    return [
        Gap(equipment, kind, duty) for duty in sorted(duties - logged, key=lambda item: item.value)
    ]


def days_run(store: Store, equipment: str, kind: str, days: tuple[date, ...]) -> int:
    return sum(1 for day in days if ran_on(store, equipment, kind, day))


def days_covered(
    store: Store, equipment: str, kind: str, duties: frozenset[Duty], days: tuple[date, ...]
) -> int:
    return sum(
        1
        for day in days
        if ran_on(store, equipment, kind, day) and store.duties.covered(equipment, day, duties)
    )
