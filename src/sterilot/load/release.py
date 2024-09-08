"""Releasing a load, which is the decision the whole record exists to support.

Everything upstream is evidence. This is where somebody says the contents may
go to a patient, and it is the one place in the department where being wrong is
not recoverable.

The rules interact rather than stacking, and that is the point:

- A load that failed its cycle is rejected whatever the indicators said.
- A load carrying an implant is held until its biological is read, so the
  presence of one item changes what the load as a whole is measured against.
- An early release is only available on a load that is held for the biological
  alone. It is never available on a load with a failed parameter, because there
  is nothing to be optimistic about.
- Cooling is a hard wait. A pack handled hot wicks whatever is on the shelf
  straight through the wrapper.
- The signature has to belong to somebody allowed to give it, and an early
  release needs a second one from somebody senior enough to carry it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import badge_number
from sterilot.indicators.chemical import ChemicalResult, Placement
from sterilot.load.build import Load
from sterilot.settings import Settings
from sterilot.staff.competency import CompetencyFile, Task
from sterilot.staff.tech import Technician
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer


class ReleaseKind(Enum):
    """How the load left, which is not the same as whether it left."""

    ROUTINE = "routine"
    IMPLANT = "implant"
    EMERGENCY = "emergency"
    HELD = "held"
    REJECTED = "rejected"

    @property
    def released(self) -> bool:
        return self in {ReleaseKind.ROUTINE, ReleaseKind.IMPLANT, ReleaseKind.EMERGENCY}

    @property
    def label(self) -> str:
        return self.value


@dataclass(frozen=True)
class BiologicalOutcome:
    """The biological result as the release decision needs to see it."""

    passed: bool
    problems: tuple[str, ...] = ()
    read_at: datetime | None = None

    @property
    def readable(self) -> bool:
        return self.read_at is not None


@dataclass(frozen=True)
class ReleaseRequest:
    """Everything the decision is made from."""

    load: Load
    cycle: SterilizerCycle
    sterilizer: Sterilizer
    at: datetime
    by: str
    chemical: dict[str, tuple[ChemicalResult, ...]] = field(default_factory=dict)
    biological: BiologicalOutcome | None = None
    wet_pack: bool = False
    air_removal_ok: bool = True
    emergency_justification: str = ""
    releaser: Technician | None = None
    authoriser: Technician | None = None
    competencies: CompetencyFile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "by", badge_number(self.by))
        if self.at < self.cycle.started_at:
            raise ValidationError("a load cannot be released before its cycle started")


@dataclass(frozen=True)
class ReleaseDecision:
    """What was decided, and everything that went into it."""

    kind: ReleaseKind
    reasons: tuple[str, ...]
    at: datetime
    by: str

    @property
    def released(self) -> bool:
        return self.kind.released

    def explain(self) -> str:
        if not self.reasons:
            return f"released {self.kind.label}"
        joined = "; ".join(self.reasons)
        return f"{self.kind.label}: {joined}"

    def __str__(self) -> str:
        return self.explain()


def _authority_problems(request: ReleaseRequest) -> list[str]:
    """Whether the badge on the release is allowed to be there."""
    person = request.releaser
    if person is None:
        return []
    found: list[str] = []
    if person.badge != request.by:
        found.append(f"the release is signed {request.by} and countersigned {person.badge}")
    refusal = person.refusal_to_release(request.cycle.day)
    if refusal is not None:
        found.append(refusal)
    if request.competencies is not None:
        gap = request.competencies.refusal(person.badge, Task.RELEASE, request.cycle.day)
        if gap is not None:
            found.append(gap)
    return found


def _chemical_problems(request: ReleaseRequest) -> list[str]:
    found: list[str] = []
    day = request.cycle.day
    method = request.cycle.method
    cycle_name = request.cycle.spec.name
    for item in request.load.items:
        results = request.chemical.get(item.asset, ())
        if not results:
            found.append(f"{item.asset} has no indicator result")
            continue
        placements = {result.placement for result in results}
        if Placement.INTERNAL not in placements and Placement.CHALLENGE_DEVICE not in placements:
            found.append(f"{item.asset} has no internal indicator")
        for result in results:
            for problem in result.problems(method, cycle_name, day):
                found.append(f"{item.asset}: {problem}")
    return found


def decide(request: ReleaseRequest, settings: Settings | None = None) -> ReleaseDecision:
    """Decide whether this load may be released."""
    rules = settings or Settings()
    hard: list[str] = list(request.cycle.failures(request.sterilizer, request.air_removal_ok))
    hard.extend(request.load.problems(request.sterilizer.capacity_units))
    hard.extend(_chemical_problems(request))
    hard.extend(_authority_problems(request))
    if request.wet_pack and rules.wet_pack_rejects_load:
        hard.append("the load came out wet")

    cooled_at = request.cycle.unavailable_until + timedelta(minutes=rules.cooling_minutes)
    waiting: list[str] = []
    if request.at < cooled_at:
        waiting.append(f"the load is still cooling until {cooled_at:%Y-%m-%d %H:%M}")

    biological = request.biological
    if biological is not None and not biological.passed:
        hard.extend(biological.problems or ("the biological indicator failed",))

    needs_biological = request.load.carries_implant and rules.implant_hold_required
    if needs_biological and (biological is None or not biological.readable):
        waiting.append("the load carries an implant and the biological is not read")

    if hard:
        return ReleaseDecision(ReleaseKind.REJECTED, tuple(hard), request.at, request.by)

    if waiting:
        return _consider_emergency(request, rules, tuple(waiting))

    kind = ReleaseKind.IMPLANT if request.load.carries_implant else ReleaseKind.ROUTINE
    return ReleaseDecision(kind, (), request.at, request.by)


def _consider_emergency(
    request: ReleaseRequest, rules: Settings, waiting: tuple[str, ...]
) -> ReleaseDecision:
    """An early release, if the department allows one and somebody signed for it."""
    if not request.emergency_justification.strip():
        return _held(request, waiting)
    if not rules.emergency_release_allowed:
        return _held(request, (*waiting, "the department does not allow early release"))
    refusal = _authorisation_refusal(request)
    if refusal is not None:
        return _held(request, (*waiting, refusal))
    signed = "" if request.authoriser is None else f" by {request.authoriser.badge}"
    reasons = (*waiting, f"released early{signed}: {request.emergency_justification.strip()}")
    return ReleaseDecision(ReleaseKind.EMERGENCY, reasons, request.at, request.by)


def _authorisation_refusal(request: ReleaseRequest) -> str | None:
    """Why the early release cannot be authorised, or None."""
    person = request.authoriser
    if person is None:
        return None
    refusal = person.refusal_to_authorise(request.cycle.day)
    if refusal is not None:
        return refusal
    if request.releaser is not None and person.badge == request.releaser.badge:
        return "an early release needs a second badge"
    return None


def _held(request: ReleaseRequest, reasons: tuple[str, ...]) -> ReleaseDecision:
    return ReleaseDecision(ReleaseKind.HELD, reasons, request.at, request.by)
