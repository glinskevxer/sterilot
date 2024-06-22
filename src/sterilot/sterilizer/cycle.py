"""A sterilizer run: the lot control number and everything under it.

The load is what went in. The cycle is what the chamber did, and it is the
thing every label in the load points back at. Keeping them apart matters
because one cycle can fail for reasons that have nothing to do with its
contents, and one load can be split across two cycles.

What is checked here is the machine and the run. Whether the contents may be
released is a separate question with more inputs, and it lives in the load
module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber, badge_number
from sterilot.methods import Method
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.lethality import TERMINAL_FLOOR_MINUTES, F0Result
from sterilot.sterilizer.lethality import evaluate as evaluate_f0
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.trace import Trace


@dataclass(frozen=True)
class SterilizerCycle:
    """One run of one chamber."""

    lot: LotControlNumber
    spec: CycleSpec
    started_at: datetime
    operator: str
    measurements: CycleMeasurements
    trace: Trace | None = None
    aborted: bool = False
    abort_reason: str = ""
    f0_floor: float = TERMINAL_FLOOR_MINUTES
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator", badge_number(self.operator))
        if self.lot.run_date != self.started_at.date():
            raise ValidationError(
                "the lot control number does not match the day the cycle ran",
                lot=self.lot.format(),
                started=self.started_at.date().isoformat(),
            )
        if self.aborted and not self.abort_reason.strip():
            raise ValidationError("an aborted cycle records why", lot=self.lot.format())
        if not self.aborted and self.abort_reason.strip():
            raise ValidationError("only an aborted cycle has a reason", lot=self.lot.format())
        if self.f0_floor <= 0:
            raise ValidationError("an F0 floor is a positive number", floor=self.f0_floor)

    @property
    def equipment(self) -> str:
        return self.lot.sterilizer

    @property
    def method(self) -> Method:
        return self.spec.method

    @property
    def day(self) -> date:
        return self.lot.run_date

    @property
    def run(self) -> int:
        return self.lot.run

    @property
    def unavailable_until(self) -> datetime:
        """When the contents can actually be touched, aeration included."""
        held = self.measurements.exposure + self.measurements.dry_time + self.method.aeration
        return self.started_at + timedelta(seconds=held.seconds)

    def f0(self) -> F0Result | None:
        """F0 for a steam cycle with a trace. None otherwise."""
        if self.trace is None or not self.method.is_steam:
            return None
        return evaluate_f0(self.trace, self.f0_floor)

    def parameter_failures(self) -> tuple[str, ...]:
        return self.spec.failures(self.measurements)

    def failures(self, sterilizer: Sterilizer, air_removal_ok: bool = True) -> tuple[str, ...]:
        """Everything wrong with this run, worst first."""
        if sterilizer.equipment != self.equipment:
            raise ValidationError(
                "that cycle did not run in that chamber",
                cycle=self.equipment,
                sterilizer=sterilizer.equipment,
            )
        found: list[str] = []
        refusal = sterilizer.refusal_for(self.method, self.day)
        if refusal is not None:
            found.append(refusal)
        if self.aborted:
            found.append(f"the cycle was aborted: {self.abort_reason}")
        if not air_removal_ok:
            found.append("the chamber had no passing air removal test that day")
        found.extend(self.parameter_failures())
        result = self.f0()
        if result is not None and not result.passed:
            found.append(result.explain())
        return tuple(found)

    def acceptable(self, sterilizer: Sterilizer, air_removal_ok: bool = True) -> bool:
        return not self.failures(sterilizer, air_removal_ok)

    def label(self) -> str:
        return self.lot.format()

    def __str__(self) -> str:
        return self.label()


def runs_on(
    cycles: tuple[SterilizerCycle, ...], equipment: str, day: date
) -> tuple[SterilizerCycle, ...]:
    """Every cycle a chamber ran on a day, in run order."""
    return tuple(
        sorted(
            (cycle for cycle in cycles if cycle.equipment == equipment and cycle.day == day),
            key=lambda cycle: cycle.run,
        )
    )


def next_run_number(cycles: tuple[SterilizerCycle, ...], equipment: str, day: date) -> int:
    earlier = runs_on(cycles, equipment, day)
    return earlier[-1].run + 1 if earlier else 1
