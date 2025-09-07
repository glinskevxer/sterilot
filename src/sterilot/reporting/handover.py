"""The shift handover.

The board says where the work is. This says what the next shift has to pick up,
which is a different list: the loads nobody has decided on, the daily tests
still owed on a machine that ran, the carts built and not delivered, and the
trays that went out and have not come back.

It is written for somebody reading it standing up, so it is short and every
line is something to do rather than something to know.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sterilot.clock import Shift, processing_day, shift_at
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.quality.log import Duty
from sterilot.reporting import coverage
from sterilot.reporting.render import Column, bullets, heading, join, pairs, table
from sterilot.settings import Settings
from sterilot.store.store import Store


@dataclass(frozen=True)
class Owed:
    """A daily test a machine that ran has not had."""

    equipment: str
    duty: Duty

    def describe(self) -> str:
        return f"{self.equipment} still owes its {self.duty.label} test"


@dataclass(frozen=True)
class Handover:
    """What the outgoing shift leaves the incoming one."""

    at: datetime
    shift: Shift
    facility: str
    undecided: tuple[LoadRecord, ...]
    held: tuple[LoadRecord, ...]
    owed: tuple[Owed, ...]
    carts_waiting: int
    trays_out: int
    loaners_not_ready: int

    @property
    def day(self) -> date:
        return processing_day(self.at)

    @property
    def nothing_to_pass_on(self) -> bool:
        return not (
            self.undecided or self.held or self.owed or self.carts_waiting or self.loaners_not_ready
        )

    def render(self) -> str:
        head = heading(
            f"{self.facility} handover {self.at:%Y-%m-%d %H:%M}, {self.shift.label} going off"
        )
        if self.nothing_to_pass_on:
            return f"{head}\nnothing outstanding, {self.trays_out} trays out to cases"
        return join(
            [
                head,
                pairs(
                    [
                        ("loads to decide", len(self.undecided)),
                        ("loads held", len(self.held)),
                        ("tests still owed", len(self.owed)),
                        ("carts waiting to go", self.carts_waiting),
                        ("loaners not ready", self.loaners_not_ready),
                        ("trays out to cases", self.trays_out),
                    ]
                ),
                self._loads(),
                bullets(item.describe() for item in self.owed),
            ]
        )

    def _loads(self) -> str:
        rows = [
            [
                record.reference,
                record.lot.format(),
                record.status.label,
                "; ".join(record.decision.reasons) if record.decision else "",
            ]
            for record in (*self.undecided, *self.held)
        ]
        if not rows:
            return ""
        return table([Column("load"), Column("lot"), Column("status"), Column("waiting on")], rows)

    def __str__(self) -> str:
        return self.render()


def build(store: Store, at: datetime, settings: Settings | None = None) -> Handover:
    """Read the handover off the store at ``at``."""
    rules = settings or Settings()
    day = processing_day(at)
    owed = tuple(Owed(gap.equipment, gap.duty) for gap in coverage.owed(store, day))
    return Handover(
        at=at,
        shift=shift_at(at),
        facility=rules.facility,
        undecided=store.loads.with_status(LoadStatus.PENDING),
        held=store.loads.with_status(LoadStatus.HELD),
        owed=owed,
        carts_waiting=len(store.carts.undelivered()),
        trays_out=len(store.issues.open_issues()),
        loaners_not_ready=len(store.loaners.not_ready(day, rules.loaner_lead_hours)),
    )
