from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.catalog.instrument import Complexity, Instrument
from sterilot.catalog.material import material_named
from sterilot.errors import ValidationError
from sterilot.repair.inspection import (
    Check,
    CheckResult,
    Finding,
    Inspection,
    checks_for,
)

AT = datetime(2024, 9, 12, 10, 0)


def clamp() -> Instrument:
    return Instrument(
        "SU-1234", "kelly forceps", "V Mueller", material_named("SS"), complexity=Complexity.HINGED
    )


def scissors() -> Instrument:
    return Instrument(
        "SU-2000",
        "metzenbaum scissors",
        "Aesculap",
        material_named("SS"),
        complexity=Complexity.HINGED,
    )


def bipolar() -> Instrument:
    return Instrument(
        "SU-3000",
        "bipolar forceps",
        "Codman",
        material_named("SS"),
        complexity=Complexity.HINGED,
        insulated=True,
    )


def suction() -> Instrument:
    return Instrument(
        "SU-9001",
        "frazier suction",
        "Pilling",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=3.0,
        lumen_length_mm=160.0,
    )


def passing(item: Instrument) -> Inspection:
    return Inspection.of(
        "ORT-0114",
        item.catalog,
        AT,
        "T-4471",
        [CheckResult(check, Finding.PASS) for check in checks_for(item)],
    )


def test_check_and_finding_lookup() -> None:
    assert Check.named("insulation") is Check.INSULATION
    assert Finding.named("FAIL") is Finding.FAIL
    assert Finding.FAIL.blocking
    assert not Finding.MINOR.blocking
    with pytest.raises(ValidationError):
        Check.named("shine")
    with pytest.raises(ValidationError):
        Finding.named("meh")


def test_every_instrument_gets_the_universal_checks() -> None:
    for item in (clamp(), suction(), bipolar()):
        assert Check.CLEANLINESS in checks_for(item)
        assert Check.CORROSION in checks_for(item)


def test_a_hinged_instrument_earns_function_and_alignment() -> None:
    wanted = checks_for(clamp())
    assert Check.FUNCTION in wanted
    assert Check.ALIGNMENT in wanted
    assert Check.LUMEN not in wanted


def test_scissors_earn_a_sharpness_check() -> None:
    assert Check.SHARPNESS in checks_for(scissors())
    assert Check.SHARPNESS not in checks_for(clamp())


def test_a_lumened_item_earns_a_lumen_check() -> None:
    assert Check.LUMEN in checks_for(suction())


def test_an_insulated_item_earns_an_insulation_check() -> None:
    assert Check.INSULATION in checks_for(bipolar())
    assert Check.INSULATION not in checks_for(clamp())


def test_an_item_that_comes_apart_earns_a_completeness_check() -> None:
    trocar = Instrument(
        "TR-1",
        "trocar",
        "Applied",
        material_named("SS"),
        complexity=Complexity.MULTIPART,
        requires_disassembly=True,
    )
    assert Check.COMPLETENESS in checks_for(trocar)


def test_the_checklist_comes_back_in_declaration_order() -> None:
    wanted = checks_for(bipolar())
    assert list(wanted) == sorted(wanted, key=lambda check: list(Check).index(check))


def test_a_finding_is_written_down() -> None:
    with pytest.raises(ValidationError):
        CheckResult(Check.FUNCTION, Finding.FAIL)
    assert CheckResult(Check.FUNCTION, Finding.FAIL, "box lock seized").note


def test_a_result_describes_itself() -> None:
    assert CheckResult(Check.FUNCTION, Finding.PASS).describe() == "function pass"
    assert CheckResult(Check.FUNCTION, Finding.MINOR, "stiff").describe() == (
        "function minor: stiff"
    )


def test_the_same_check_cannot_be_recorded_twice() -> None:
    with pytest.raises(ValidationError):
        Inspection.of(
            "ORT-0114",
            "SU-1234",
            AT,
            "T-4471",
            [CheckResult(Check.FUNCTION, Finding.PASS), CheckResult(Check.FUNCTION, Finding.PASS)],
        )


def test_a_complete_inspection_passes() -> None:
    assert passing(clamp()).passed(clamp())
    assert passing(clamp()).problems(clamp()) == ()


def test_an_inspection_judged_against_another_item_is_refused() -> None:
    with pytest.raises(ValidationError):
        passing(clamp()).problems(scissors())


def test_a_missing_check_is_named() -> None:
    results = [
        CheckResult(check, Finding.PASS)
        for check in checks_for(bipolar())
        if check is not Check.INSULATION
    ]
    inspection = Inspection.of("ORT-0114", "SU-3000", AT, "T-4471", results)
    assert inspection.problems(bipolar()) == ("insulation was not checked",)


def test_a_failed_check_is_named_with_its_note() -> None:
    results = [
        CheckResult(check, Finding.PASS)
        for check in checks_for(clamp())
        if check is not Check.FUNCTION
    ]
    results.append(CheckResult(Check.FUNCTION, Finding.FAIL, "box lock seized"))
    inspection = Inspection.of("ORT-0114", "SU-1234", AT, "T-4471", results)
    assert inspection.problems(clamp()) == ("function failed: box lock seized",)
    assert not inspection.passed(clamp())


def test_a_minor_finding_does_not_stop_the_tray() -> None:
    results = [
        CheckResult(check, Finding.PASS)
        for check in checks_for(clamp())
        if check is not Check.ALIGNMENT
    ]
    results.append(CheckResult(Check.ALIGNMENT, Finding.MINOR, "jaws slightly proud"))
    inspection = Inspection.of("ORT-0114", "SU-1234", AT, "T-4471", results)
    assert inspection.passed(clamp())
    assert len(inspection.minor_findings()) == 1


def test_result_lookup_and_normalised_identifiers() -> None:
    inspection = Inspection.of("ort 0114", "su 1234", AT, "t 4471", [])
    assert inspection.asset == "ORT-0114"
    assert inspection.catalog == "SU-1234"
    assert inspection.by == "T-4471"
    assert inspection.result_for(Check.FUNCTION) is None
