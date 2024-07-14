"""The load record, and the register that holds them.

Once a decision has been made about a load, the load stops being a plan and
becomes a fact somebody may have to account for years later. The record binds
the three things a question will start from: what was in it, which cycle ran
it, and what was decided.

The register exists because every interesting question is a search. Which loads
did this chamber run last Tuesday. Where is tray ORT-0114. What is still
sitting held.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.ids import LotControlNumber, asset_tag, normalise_code
from sterilot.load.build import Load
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.sterilizer.cycle import SterilizerCycle


class LoadStatus(Enum):
    """Where a load stands."""

    PENDING = "pending"
    RELEASED = "released"
    HELD = "held"
    REJECTED = "rejected"
    RECALLED = "recalled"

    @property
    def label(self) -> str:
        return self.value

    @property
    def contents_usable(self) -> bool:
        return self is LoadStatus.RELEASED


@dataclass(frozen=True)
class LoadRecord:
    """One load, its cycle, and whatever has been decided about it."""

    load: Load
    cycle: SterilizerCycle
    decision: ReleaseDecision | None = None
    recalled_at: datetime | None = None
    recall_reason: str = ""

    def __post_init__(self) -> None:
        if self.load.method is not self.cycle.method:
            raise ValidationError(
                "the load was built for a different method",
                load=self.load.reference,
                load_method=self.load.method.value,
                cycle_method=self.cycle.method.value,
            )
        if self.recalled_at is not None and not self.recall_reason.strip():
            raise ValidationError("a recall records why", load=self.load.reference)

    @property
    def reference(self) -> str:
        return self.load.reference

    @property
    def lot(self) -> LotControlNumber:
        return self.cycle.lot

    @property
    def status(self) -> LoadStatus:
        if self.recalled_at is not None:
            return LoadStatus.RECALLED
        if self.decision is None:
            return LoadStatus.PENDING
        if self.decision.released:
            return LoadStatus.RELEASED
        if self.decision.kind is ReleaseKind.REJECTED:
            return LoadStatus.REJECTED
        return LoadStatus.HELD

    @property
    def released(self) -> bool:
        return self.status is LoadStatus.RELEASED

    def holds(self, asset: str) -> bool:
        wanted = asset_tag(asset)
        return wanted in self.load.assets()

    def decided(self, decision: ReleaseDecision) -> LoadRecord:
        if self.recalled_at is not None:
            raise ConflictError("that load was recalled", load=self.reference)
        return LoadRecord(self.load, self.cycle, decision, self.recalled_at, self.recall_reason)

    def recalled(self, at: datetime, reason: str) -> LoadRecord:
        if self.recalled_at is not None:
            raise ConflictError("that load is already recalled", load=self.reference)
        return LoadRecord(self.load, self.cycle, self.decision, at, reason)

    def summary(self) -> str:
        return f"{self.reference} {self.lot.format()} {self.status.label}"

    def __str__(self) -> str:
        return self.summary()


@dataclass(frozen=True)
class LoadRegister:
    """Every load record, keyed by reference."""

    records: tuple[LoadRecord, ...] = ()

    @classmethod
    def of(cls, records: Iterable[LoadRecord]) -> LoadRegister:
        register = cls()
        for record in records:
            register = register.with_record(record)
        return register

    def with_record(self, record: LoadRecord) -> LoadRegister:
        if any(item.reference == record.reference for item in self.records):
            raise ConflictError("that load reference is already used", load=record.reference)
        return LoadRegister((*self.records, record))

    def replacing(self, record: LoadRecord) -> LoadRegister:
        found = False
        changed: list[LoadRecord] = []
        for item in self.records:
            if item.reference == record.reference:
                changed.append(record)
                found = True
            else:
                changed.append(item)
        if not found:
            raise NotFoundError("no load with that reference", load=record.reference)
        return LoadRegister(tuple(changed))

    def get(self, reference: str) -> LoadRecord:
        wanted = normalise_code(reference, field="load reference")
        for record in self.records:
            if record.reference == wanted:
                return record
        raise NotFoundError("no load with that reference", load=wanted)

    def for_lot(self, lot: LotControlNumber) -> tuple[LoadRecord, ...]:
        return tuple(record for record in self.records if record.lot == lot)

    def for_asset(self, asset: str) -> tuple[LoadRecord, ...]:
        wanted = asset_tag(asset)
        return tuple(record for record in self.records if record.holds(wanted))

    def on_equipment(self, equipment: str, day: date | None = None) -> tuple[LoadRecord, ...]:
        found = [record for record in self.records if record.lot.sterilizer == equipment.upper()]
        if day is not None:
            found = [record for record in found if record.lot.run_date == day]
        return tuple(sorted(found, key=lambda record: (record.lot.run_date, record.lot.run)))

    def with_status(self, status: LoadStatus) -> tuple[LoadRecord, ...]:
        return tuple(record for record in self.records if record.status is status)

    def undecided(self) -> tuple[LoadRecord, ...]:
        return self.with_status(LoadStatus.PENDING)
