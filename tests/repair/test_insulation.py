from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.catalog.instrument import Complexity, Instrument
from sterilot.catalog.material import material_named
from sterilot.errors import ValidationError
from sterilot.repair.insulation import InsulationLog, InsulationTest

AT = datetime(2024, 9, 12, 10, 0)


def bipolar() -> Instrument:
    return Instrument(
        "SU-3000",
        "bipolar forceps",
        "Codman",
        material_named("SS"),
        complexity=Complexity.HINGED,
        insulated=True,
    )


def clamp() -> Instrument:
    return Instrument(
        "SU-1234", "kelly forceps", "V Mueller", material_named("SS"), complexity=Complexity.HINGED
    )


def run_test(**changes: object) -> InsulationTest:
    values: dict[str, object] = {
        "asset": "bip 0031",
        "catalog": "su 3000",
        "at": AT,
        "by": "t 4471",
        "tester": "it 1",
        "voltage": 2500,
        "passed": True,
    }
    values.update(changes)
    return InsulationTest(**values)  # type: ignore[arg-type]


def test_identifiers_are_normalised() -> None:
    made = run_test()
    assert made.asset == "BIP-0031"
    assert made.catalog == "SU-3000"
    assert made.tester == "IT-1"
    assert made.day == date(2024, 9, 12)


def test_a_test_runs_at_a_voltage() -> None:
    with pytest.raises(ValidationError):
        run_test(voltage=0)


def test_a_passing_test_found_no_defect() -> None:
    with pytest.raises(ValidationError):
        run_test(defect_at_cm=12.0)


def test_a_failing_test_says_where_the_defect_is() -> None:
    with pytest.raises(ValidationError):
        run_test(passed=False)
    with pytest.raises(ValidationError):
        run_test(passed=False, defect_at_cm=-1.0)


def test_a_good_test_on_an_insulated_item_passes() -> None:
    assert run_test().acceptable(bipolar())
    assert run_test().describe() == "BIP-0031 passed at 2500 V"


def test_a_test_on_an_uninsulated_item_is_meaningless() -> None:
    made = run_test(catalog="SU-1234")
    assert "that instrument has no insulation to test" in made.problems(clamp())


def test_a_test_below_the_minimum_voltage_is_named() -> None:
    problems = run_test(voltage=1200).problems(bipolar())
    assert problems == ("the test ran at 1200 V, below 2000",)


def test_a_failed_test_names_the_defect_position() -> None:
    made = run_test(passed=False, defect_at_cm=11.5)
    assert made.problems(bipolar()) == ("insulation failed 11.5 cm from the tip",)
    assert str(made) == "BIP-0031 failed at 2500 V, defect 11.5 cm from the tip"


def test_a_test_judged_against_another_item_is_refused() -> None:
    with pytest.raises(ValidationError):
        run_test().problems(clamp())


def test_the_log_keeps_tests_in_order_and_finds_the_latest() -> None:
    log = InsulationLog.of([run_test(at=datetime(2024, 9, 20, 9, 0)), run_test()])
    latest = log.latest_for("BIP-0031")
    assert latest is not None
    assert latest.at == datetime(2024, 9, 20, 9, 0)
    assert len(log.for_asset("bip 0031")) == 2


def test_in_service_follows_the_last_test() -> None:
    log = InsulationLog.of([run_test()])
    assert log.in_service("BIP-0031")
    log = log.with_test(run_test(at=datetime(2024, 9, 20, 9, 0), passed=False, defect_at_cm=4.0))
    assert not log.in_service("BIP-0031")
    assert len(log.failures()) == 1


def test_an_untested_instrument_is_not_in_service() -> None:
    assert not InsulationLog().in_service("BIP-0031")


def test_an_uninsulated_instrument_needs_no_test() -> None:
    assert InsulationLog().refusal("SU-0001", clamp(), AT) is None


def test_an_insulated_instrument_that_was_never_tested_is_refused() -> None:
    assert InsulationLog().refusal("BIP-0031", bipolar(), AT) == (
        "the instrument has never been insulation tested"
    )


def test_a_failed_test_keeps_the_instrument_out() -> None:
    log = InsulationLog.of([run_test(passed=False, defect_at_cm=4.0)])
    refusal = log.refusal("BIP-0031", bipolar(), datetime(2024, 9, 12, 8, 0))
    assert refusal is not None
    assert "failed at 2500 V" in refusal


def test_a_test_from_before_this_reprocessing_does_not_count() -> None:
    log = InsulationLog.of([run_test(at=datetime(2024, 9, 1, 9, 0))])
    assert log.refusal("BIP-0031", bipolar(), datetime(2024, 9, 12, 6, 0)) == (
        "the last insulation test predates the current reprocessing"
    )


def test_a_test_taken_during_this_reprocessing_covers_it() -> None:
    log = InsulationLog.of([run_test()])
    assert log.refusal("BIP-0031", bipolar(), datetime(2024, 9, 12, 6, 0)) is None
