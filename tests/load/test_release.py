from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.indicators.chemical import (
    ChemicalIndicator,
    ChemicalResult,
    IndicatorClass,
    Outcome,
    Placement,
)
from sterilot.interval import DateRange
from sterilot.load.build import Load, LoadItem
from sterilot.load.release import (
    BiologicalOutcome,
    ReleaseKind,
    ReleaseRequest,
    decide,
)
from sterilot.methods import Method
from sterilot.settings import Settings
from sterilot.staff.competency import Competency, CompetencyFile, Task
from sterilot.staff.tech import Certification, Role, Technician
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.pressure import saturation_pressure
from sterilot.units.temperature import Temperature

DAY = date(2024, 7, 8)
START = datetime(2024, 7, 8, 8, 0)
COOLED = datetime(2024, 7, 8, 9, 30)


def chamber() -> Sterilizer:
    return Sterilizer(
        "AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC, Method.STEAM_IUSS})
    )


def measurements(**changes: object) -> CycleMeasurements:
    values: dict[str, object] = {
        "hold_temperature": Temperature(133.0),
        "exposure": Duration.of_minutes(4),
        "dry_time": Duration.of_minutes(31),
        "chamber_pressure": saturation_pressure(Temperature(133.0)),
        "conditioning_pulses": 4,
    }
    values.update(changes)
    return CycleMeasurements(**values)  # type: ignore[arg-type]


def cycle(**changes: object) -> SterilizerCycle:
    values: dict[str, object] = {
        "lot": LotControlNumber("AC-1", DAY, 2),
        "spec": CycleSpec.standard(Method.STEAM_PREVAC),
        "started_at": START,
        "operator": "T-4471",
        "measurements": measurements(),
        "trace": Trace.flat(START, 133.0, 240.0, step=20.0),
    }
    values.update(changes)
    return SterilizerCycle(**values)  # type: ignore[arg-type]


def strip(
    placement: Placement = Placement.INTERNAL, outcome: Outcome = Outcome.PASS
) -> ChemicalResult:
    indicator = ChemicalIndicator(
        IndicatorClass.INTEGRATING,
        "CI-24B09",
        date(2025, 1, 31),
        frozenset({Method.STEAM_PREVAC}),
    )
    return ChemicalResult(indicator, placement, outcome, COOLED, "T-4471")


def load(**changes: object) -> Load:
    values: dict[str, object] = {
        "reference": "LD-4412",
        "method": Method.STEAM_PREVAC,
        "items": (LoadItem("ORT-0114", "ORT-MAJOR"),),
        "built_by": "T-4471",
        "built_at": datetime(2024, 7, 8, 7, 30),
    }
    values.update(changes)
    return Load(**values)  # type: ignore[arg-type]


def request(**changes: object) -> ReleaseRequest:
    values: dict[str, object] = {
        "load": load(),
        "cycle": cycle(),
        "sterilizer": chamber(),
        "at": COOLED,
        "by": "T-4471",
        "chemical": {"ORT-0114": (strip(Placement.EXTERNAL), strip())},
    }
    values.update(changes)
    return ReleaseRequest(**values)  # type: ignore[arg-type]


def test_a_release_cannot_predate_its_cycle() -> None:
    with pytest.raises(ValidationError):
        request(at=datetime(2024, 7, 8, 7, 0))


def test_a_clean_load_is_released_routinely() -> None:
    decision = decide(request())
    assert decision.released
    assert decision.kind is ReleaseKind.ROUTINE
    assert decision.reasons == ()
    assert decision.explain() == "released routine"


def test_a_failed_cycle_rejects_the_load_whatever_the_strips_said() -> None:
    cold = cycle(measurements=measurements(hold_temperature=Temperature(126.0)))
    decision = decide(request(cycle=cold))
    assert not decision.released
    assert decision.kind is ReleaseKind.REJECTED
    assert any("chamber 126.0 C" in item for item in decision.reasons)


def test_a_missing_internal_indicator_rejects_the_item() -> None:
    decision = decide(request(chemical={"ORT-0114": (strip(Placement.EXTERNAL),)}))
    assert decision.kind is ReleaseKind.REJECTED
    assert "ORT-0114 has no internal indicator" in decision.reasons


def test_an_item_with_no_indicator_at_all_is_named() -> None:
    decision = decide(request(chemical={}))
    assert "ORT-0114 has no indicator result" in decision.reasons


def test_a_failed_strip_is_named_against_its_tray() -> None:
    decision = decide(
        request(chemical={"ORT-0114": (strip(Placement.EXTERNAL), strip(outcome=Outcome.FAIL))})
    )
    assert "ORT-0114: the internal indicator failed" in decision.reasons


def test_a_challenge_device_stands_in_for_the_internal_strip() -> None:
    decision = decide(request(chemical={"ORT-0114": (strip(Placement.CHALLENGE_DEVICE),)}))
    assert decision.released


def test_a_wet_load_is_rejected() -> None:
    decision = decide(request(wet_pack=True))
    assert decision.kind is ReleaseKind.REJECTED
    assert "the load came out wet" in decision.reasons


def test_a_department_that_tolerates_wet_packs_releases_anyway() -> None:
    decision = decide(request(wet_pack=True), Settings(wet_pack_rejects_load=False))
    assert decision.released


def test_a_load_still_cooling_is_held() -> None:
    decision = decide(request(at=datetime(2024, 7, 8, 8, 40)))
    assert not decision.released
    assert decision.kind is ReleaseKind.HELD
    assert "still cooling" in decision.reasons[0]


def test_an_implant_load_is_held_until_the_biological_is_read() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    decision = decide(
        request(load=implant, chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())})
    )
    assert decision.kind is ReleaseKind.HELD
    assert "the load carries an implant and the biological is not read" in decision.reasons


def test_an_implant_load_with_a_read_biological_is_released() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    outcome = BiologicalOutcome(passed=True, read_at=COOLED)
    decision = decide(
        request(
            load=implant,
            biological=outcome,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
        )
    )
    assert decision.kind is ReleaseKind.IMPLANT
    assert decision.released


def test_a_department_that_does_not_hold_implants_releases_routinely() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    decision = decide(
        request(load=implant, chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())}),
        Settings(implant_hold_required=False),
    )
    assert decision.kind is ReleaseKind.IMPLANT
    assert decision.released


def test_a_failed_biological_rejects_the_load() -> None:
    outcome = BiologicalOutcome(
        passed=False, problems=("the biological indicator grew",), read_at=COOLED
    )
    decision = decide(request(biological=outcome))
    assert decision.kind is ReleaseKind.REJECTED
    assert "the biological indicator grew" in decision.reasons


def test_a_failed_biological_with_no_detail_still_rejects() -> None:
    decision = decide(request(biological=BiologicalOutcome(passed=False, read_at=COOLED)))
    assert decision.kind is ReleaseKind.REJECTED
    assert "the biological indicator failed" in decision.reasons


def test_an_early_release_needs_a_justification() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    base = request(load=implant, chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())})
    assert decide(base).kind is ReleaseKind.HELD
    early = decide(
        request(
            load=implant,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
            emergency_justification="trauma case in room 3",
        )
    )
    assert early.kind is ReleaseKind.EMERGENCY
    assert early.released
    assert "released early: trauma case in room 3" in early.reasons


def test_an_early_release_is_refused_where_the_department_forbids_it() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    decision = decide(
        request(
            load=implant,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
            emergency_justification="trauma case",
        ),
        Settings(emergency_release_allowed=False),
    )
    assert decision.kind is ReleaseKind.HELD
    assert "the department does not allow early release" in decision.reasons


def test_an_early_release_cannot_rescue_a_failed_cycle() -> None:
    cold = cycle(measurements=measurements(hold_temperature=Temperature(126.0)))
    decision = decide(request(cycle=cold, emergency_justification="trauma case"))
    assert decision.kind is ReleaseKind.REJECTED


def test_a_missing_air_removal_test_rejects_the_load() -> None:
    decision = decide(request(air_removal_ok=False))
    assert decision.kind is ReleaseKind.REJECTED
    assert "the chamber had no passing air removal test that day" in decision.reasons


def test_a_load_that_should_not_have_been_built_is_rejected() -> None:
    bad = load(
        method=Method.STEAM_IUSS,
        items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),),
    )
    iuss = cycle(
        spec=CycleSpec.standard(Method.STEAM_IUSS),
        measurements=measurements(dry_time=Duration.zero()),
    )
    decision = decide(
        request(
            load=bad,
            cycle=iuss,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
            at=datetime(2024, 7, 8, 12, 0),
        )
    )
    assert decision.kind is ReleaseKind.REJECTED
    assert "an implant cannot go through an immediate use cycle" in decision.reasons


def test_the_decision_carries_who_and_when() -> None:
    decision = decide(request(by="t 9002"))
    assert decision.by == "T-9002"
    assert decision.at == COOLED


def test_only_three_kinds_count_as_released() -> None:
    released = {kind for kind in ReleaseKind if kind.released}
    assert released == {ReleaseKind.ROUTINE, ReleaseKind.IMPLANT, ReleaseKind.EMERGENCY}


def certified(badge: str = "T-4471", role: Role = Role.TECHNICIAN) -> Technician:
    return Technician(
        badge,
        "R Ferreira",
        role,
        certifications=(
            Certification("HSPA", "CRCST-1", DateRange(date(2023, 1, 1), date(2026, 1, 1))),
        ),
    )


def signed_off(badge: str = "T-4471") -> CompetencyFile:
    return CompetencyFile.of(
        [Competency(badge, Task.RELEASE, date(2024, 3, 1), "T-9500", observations=3)]
    )


def test_a_certified_releaser_changes_nothing() -> None:
    decision = decide(request(releaser=certified(), competencies=signed_off()))
    assert decision.kind is ReleaseKind.ROUTINE


def test_a_trainee_cannot_sign_a_release() -> None:
    decision = decide(request(releaser=certified(role=Role.TRAINEE)))
    assert decision.kind is ReleaseKind.REJECTED
    assert "a trainee does not sign a release" in decision.reasons


def test_a_releaser_without_the_competency_is_refused() -> None:
    decision = decide(request(releaser=certified(), competencies=CompetencyFile()))
    assert decision.kind is ReleaseKind.REJECTED
    assert "T-4471 has never been assessed on release" in decision.reasons


def test_the_signature_and_the_badge_have_to_agree() -> None:
    decision = decide(request(by="T-9002", releaser=certified(), competencies=signed_off()))
    assert decision.kind is ReleaseKind.REJECTED
    assert "the release is signed T-9002 and countersigned T-4471" in decision.reasons


def test_an_early_release_needs_a_lead_to_authorise_it() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    decision = decide(
        request(
            load=implant,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
            emergency_justification="trauma case",
            authoriser=certified("T-9002", Role.TECHNICIAN),
        )
    )
    assert decision.kind is ReleaseKind.HELD
    assert "a technician does not authorise an early release" in decision.reasons


def test_an_early_release_authorised_by_a_lead_goes_through() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    decision = decide(
        request(
            load=implant,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
            emergency_justification="trauma case",
            releaser=certified(),
            competencies=signed_off(),
            authoriser=certified("T-9002", Role.LEAD),
        )
    )
    assert decision.kind is ReleaseKind.EMERGENCY
    assert "released early by T-9002: trauma case" in decision.reasons


def test_the_same_badge_cannot_release_and_authorise() -> None:
    implant = load(items=(LoadItem("IMP-0001", "IMP-KNEE", implant=True),))
    lead = certified("T-4471", Role.LEAD)
    decision = decide(
        request(
            load=implant,
            chemical={"IMP-0001": (strip(Placement.EXTERNAL), strip())},
            emergency_justification="trauma case",
            releaser=lead,
            competencies=signed_off(),
            authoriser=lead,
        )
    )
    assert decision.kind is ReleaseKind.HELD
    assert "an early release needs a second badge" in decision.reasons
