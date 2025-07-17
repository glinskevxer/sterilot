"""The board on the wall.

One screen, refreshed by running the command again, showing where the work is
right now rather than what happened yesterday. A supervisor should be able to
stand in front of it and see the next thing to do without asking anybody.

Nothing here is new information. It is the four questions the department asks
each other all day, in the order they get asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sterilot.assets.lifecycle import Stage
from sterilot.clock import processing_day
from sterilot.load.record import LoadStatus
from sterilot.reporting.render import Column, heading, join, pairs, table
from sterilot.settings import Settings
from sterilot.store.store import Store


@dataclass(frozen=True)
class Board:
    """Where the work is."""

    at: datetime
    facility: str
    stages: dict[Stage, int]
    held: int
    pending: int
    out: int
    carts_waiting: int
    on_hand: dict[str, int]
    to_build: tuple[tuple[str, int], ...]

    @property
    def in_progress(self) -> int:
        return sum(
            count
            for stage, count in self.stages.items()
            if stage
            in {
                Stage.SOILED,
                Stage.DECONTAMINATION,
                Stage.CLEAN,
                Stage.ASSEMBLED,
                Stage.STERILIZING,
            }
        )

    @property
    def quiet(self) -> bool:
        return not (self.in_progress or self.held or self.pending or self.to_build)

    def render(self) -> str:
        return join(
            [
                heading(f"{self.facility} board {self.at:%Y-%m-%d %H:%M}"),
                pairs(
                    [
                        ("trays in the loop", self.in_progress),
                        ("loads waiting on a decision", self.pending),
                        ("loads held", self.held),
                        ("trays out to cases", self.out),
                        ("carts waiting to go", self.carts_waiting),
                    ]
                ),
                self._stages(),
                self._build(),
            ]
        )

    def _stages(self) -> str:
        rows = [
            [stage.label, self.stages.get(stage, 0)] for stage in Stage if self.stages.get(stage, 0)
        ]
        if not rows:
            return ""
        return table([Column("stage"), Column("trays", align="right")], rows)

    def _build(self) -> str:
        if not self.to_build:
            return ""
        return table(
            [Column("set"), Column("on hand", align="right"), Column("build", align="right")],
            [[code, self.on_hand.get(code, 0), short] for code, short in self.to_build],
        )

    def __str__(self) -> str:
        return self.render()


def build(store: Store, at: datetime, settings: Settings | None = None) -> Board:
    """Read the board off the store."""
    rules = settings or Settings()
    counts = store.trays.counts_by_stage()
    on_hand = store.packages.on_hand(at, rules)
    plan = store.packages.storage_map()
    return Board(
        at=at,
        facility=rules.facility,
        stages=counts,
        held=len(store.loads.with_status(LoadStatus.HELD)),
        pending=len(store.loads.with_status(LoadStatus.PENDING)),
        out=len(store.issues.open_issues()),
        carts_waiting=len(store.carts.undelivered()),
        on_hand=on_hand,
        to_build=plan.build_list(on_hand),
    )


def board_day(when: datetime) -> date:
    """The processing day the board belongs to, third shift kept whole."""
    return processing_day(when)
