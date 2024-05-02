"""Wash programs and the cycles run against them.

A program is what the machine was told to do. A cycle is what happened. The
whole value of keeping both is that they can be compared, phase by phase, and
that a cycle which skipped its thermal rinse is caught here rather than three
steps later when the tray is already wrapped.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from sterilot.decon.a0 import ROUTINE_FLOOR, A0Result
from sterilot.decon.a0 import evaluate as evaluate_a0
from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import ValidationError
from sterilot.ids import badge_number, equipment_id, normalise_code
from sterilot.tolerance import Band
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


class Phase(Enum):
    """The steps a wash program can contain, in the order they must run."""

    PREWASH = "prewash"
    WASH = "wash"
    RINSE = "rinse"
    THERMAL = "thermal"
    DRY = "dry"
    LUBRICATION = "lubrication"

    @property
    def order(self) -> int:
        return list(Phase).index(self)

    @property
    def label(self) -> str:
        return self.value

    @classmethod
    def named(cls, value: str) -> Phase:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such wash phase", value=value)


@dataclass(frozen=True)
class PhaseSpec:
    """What one phase of a program is supposed to do."""

    phase: Phase
    minimum: Duration
    temperature: Band | None = None
    detergent: str = ""

    def __post_init__(self) -> None:
        if self.minimum.seconds <= 0:
            raise ValidationError("a phase has to last", phase=self.phase.value)


@dataclass(frozen=True)
class Program:
    """A named wash program."""

    name: str
    phases: tuple[PhaseSpec, ...]
    washer_class: WasherClass = WasherClass.SINGLE_CHAMBER
    a0_floor: float | None = ROUTINE_FLOOR

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalise_code(self.name, field="program name"))
        if not self.phases:
            raise ValidationError("a program needs a phase", name=self.name)
        seen = [spec.phase for spec in self.phases]
        if len(set(seen)) != len(seen):
            raise ValidationError("a phase appears twice in the program", name=self.name)
        if [phase.order for phase in seen] != sorted(phase.order for phase in seen):
            raise ValidationError("the program's phases are out of order", name=self.name)
        if self.a0_floor is not None and not self.washer_class.disinfects:
            raise ValidationError(
                "only a disinfecting machine can be held to an A0 floor", name=self.name
            )
        if self.a0_floor is not None and Phase.THERMAL not in seen:
            raise ValidationError("an A0 floor needs a thermal phase to reach it", name=self.name)

    @classmethod
    def of(cls, name: str, specs: Iterable[PhaseSpec], **values: object) -> Program:
        return cls(name, tuple(specs), **values)  # type: ignore[arg-type]

    def spec_for(self, phase: Phase) -> PhaseSpec | None:
        for spec in self.phases:
            if spec.phase is phase:
                return spec
        return None

    @property
    def disinfects(self) -> bool:
        return self.a0_floor is not None


@dataclass(frozen=True)
class PhaseRecord:
    """What one phase actually did."""

    phase: Phase
    ran_for: Duration
    peak: Temperature | None = None


@dataclass(frozen=True)
class WasherCycle:
    """One run of one program on one machine."""

    equipment: str
    program: Program
    number: int
    started_at: datetime
    operator: str
    phases: tuple[PhaseRecord, ...] = field(default_factory=tuple)
    trace: Trace | None = None
    aborted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        object.__setattr__(self, "operator", badge_number(self.operator))
        if self.number < 1:
            raise ValidationError("cycle numbers start at one", number=self.number)

    @property
    def day(self) -> date:
        return self.started_at.date()

    def record_for(self, phase: Phase) -> PhaseRecord | None:
        for record in self.phases:
            if record.phase is phase:
                return record
        return None

    def a0(self) -> A0Result | None:
        if self.trace is None or self.program.a0_floor is None:
            return None
        return evaluate_a0(self.trace, self.program.a0_floor)

    def failures(self, washer: Washer) -> tuple[str, ...]:
        """Everything wrong with this cycle, worst first."""
        found: list[str] = []
        if washer.equipment != self.equipment:
            raise ValidationError(
                "that cycle did not run on that machine",
                cycle=self.equipment,
                washer=washer.equipment,
            )
        refusal = washer.refusal_on(self.day)
        if refusal is not None:
            found.append(refusal)
        if washer.washer_class is not self.program.washer_class:
            found.append("the program is not written for that class of machine")
        if self.aborted:
            found.append("the cycle was aborted")
        for spec in self.program.phases:
            record = self.record_for(spec.phase)
            if record is None:
                found.append(f"the {spec.phase.label} phase did not run")
                continue
            if record.ran_for.seconds < spec.minimum.seconds:
                short = record.ran_for.shortfall_against(spec.minimum)
                found.append(
                    f"the {spec.phase.label} phase was {short.spelled()} short of "
                    f"{spec.minimum.spelled()}"
                )
            if spec.temperature is not None:
                if record.peak is None:
                    found.append(f"the {spec.phase.label} phase has no temperature")
                else:
                    reading = spec.temperature.evaluate(record.peak.celsius)
                    if not reading.passed:
                        found.append(f"{spec.phase.label}: {reading.explain(unit='C')}")
        result = self.a0()
        if result is not None and not result.passed:
            found.append(result.explain())
        elif self.program.disinfects and self.trace is None:
            found.append("the cycle has no trace to compute A0 from")
        return tuple(found)

    def passed(self, washer: Washer) -> bool:
        return not self.failures(washer)
