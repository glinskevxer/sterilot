"""Retention: what may be deleted, and what may never be.

Hospitals keep sterilization records for years, and the exact number is a local
decision, so it is a setting rather than a constant. What is not a local
decision is the shape of the rule:

A load record is never removed while anything about it is unresolved. A cycle
is never removed while a load still points at it. An audit entry is never
removed at all, because an audit trail with a hole in it is not an audit trail.

Everything here reports before it removes, and the removal runs in one
transaction so a purge interrupted halfway leaves the file as it was.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sterilot.errors import ValidationError
from sterilot.load.record import LoadStatus
from sterilot.store import rows
from sterilot.store.db import Database

MINIMUM_RETENTION_YEARS = 3


@dataclass(frozen=True)
class PurgePlan:
    """What a purge would remove."""

    before: date
    loads: int
    cycles: int
    wash_cycles: int
    packages: int
    kept_open: int

    @property
    def total(self) -> int:
        return self.loads + self.cycles + self.wash_cycles + self.packages

    @property
    def empty(self) -> bool:
        return self.total == 0

    def describe(self) -> str:
        return (
            f"before {self.before.isoformat()}: {self.loads} loads, {self.cycles} cycles,"
            f" {self.wash_cycles} wash cycles, {self.packages} packages"
            f" ({self.kept_open} kept, still open)"
        )


def cutoff(today: date, years: int) -> date:
    """The day before which records may go."""
    if years < MINIMUM_RETENTION_YEARS:
        raise ValidationError(
            "that is below the retention floor",
            years=years,
            floor=MINIMUM_RETENTION_YEARS,
        )
    return date(today.year - years, today.month, today.day)


_CLOSED = ", ".join(
    f"'{status.value}'" for status in LoadStatus if status is not LoadStatus.PENDING
)


def plan(db: Database, before: date) -> PurgePlan:
    """Count what a purge would take, without taking it."""
    stamp = rows.put_date(before)
    loads = db.scalar(
        "SELECT count(*) FROM load_record l JOIN sterilizer_cycle c ON c.lot = l.lot"
        f" WHERE c.run_date < ? AND l.status IN ({_CLOSED})",
        [stamp],
    )
    open_loads = db.scalar(
        "SELECT count(*) FROM load_record l JOIN sterilizer_cycle c ON c.lot = l.lot"
        " WHERE c.run_date < ? AND l.status = ?",
        [stamp, LoadStatus.PENDING.value],
    )
    cycles = db.scalar(
        "SELECT count(*) FROM sterilizer_cycle WHERE run_date < ? AND lot NOT IN"
        " (SELECT lot FROM load_record WHERE status = ?)",
        [stamp, LoadStatus.PENDING.value],
    )
    wash = db.scalar(
        "SELECT count(*) FROM washer_cycle WHERE started_at < ?",
        [f"{before.isoformat()}T00:00:00"],
    )
    packages = db.scalar(
        "SELECT count(*) FROM package WHERE sterilized_at < ?",
        [f"{before.isoformat()}T00:00:00"],
    )
    return PurgePlan(
        before=before,
        loads=int(loads or 0),
        cycles=int(cycles or 0),
        wash_cycles=int(wash or 0),
        packages=int(packages or 0),
        kept_open=int(open_loads or 0),
    )


def purge(db: Database, before: date) -> PurgePlan:
    """Remove what the plan describes, all of it or none of it."""
    counted = plan(db, before)
    stamp = rows.put_date(before)
    moment = f"{before.isoformat()}T00:00:00"
    with db.transaction():
        db.execute(
            "DELETE FROM load_item WHERE reference IN (SELECT l.reference FROM load_record l"
            " JOIN sterilizer_cycle c ON c.lot = l.lot"
            f" WHERE c.run_date < ? AND l.status IN ({_CLOSED}))",
            [stamp],
        )
        db.execute(
            "DELETE FROM load_record WHERE reference IN (SELECT l.reference FROM load_record l"
            " JOIN sterilizer_cycle c ON c.lot = l.lot"
            f" WHERE c.run_date < ? AND l.status IN ({_CLOSED}))",
            [stamp],
        )
        db.execute(
            "DELETE FROM sterilizer_cycle WHERE run_date < ? AND lot NOT IN"
            " (SELECT lot FROM load_record)",
            [stamp],
        )
        db.execute("DELETE FROM washer_phase WHERE started_at < ?", [moment])
        db.execute("DELETE FROM washer_cycle WHERE started_at < ?", [moment])
        db.execute(
            "DELETE FROM package_event WHERE (asset, lot) IN"
            " (SELECT asset, lot FROM package WHERE sterilized_at < ?)",
            [moment],
        )
        db.execute("DELETE FROM package WHERE sterilized_at < ?", [moment])
    return counted
