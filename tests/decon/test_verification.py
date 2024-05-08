from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.decon.verification import Verification, VerificationKind, VerificationLog
from sterilot.errors import ValidationError

MORNING = datetime(2024, 5, 1, 7, 15)


def soil(at: datetime = MORNING, passed: bool = True, equipment: str = "WD-2") -> Verification:
    return Verification(VerificationKind.SOIL_DEVICE, equipment, at, "T-4471", visual_pass=passed)


def test_check_kind_lookup_and_units() -> None:
    assert VerificationKind.named("soil device") is VerificationKind.SOIL_DEVICE
    assert VerificationKind.named("ATP") is VerificationKind.ATP
    assert VerificationKind.ATP.unit == "RLU"
    assert VerificationKind.SOIL_DEVICE.is_visual
    assert not VerificationKind.PROTEIN.is_visual
    with pytest.raises(ValidationError):
        VerificationKind.named("swab")


def test_only_measured_tests_have_a_band() -> None:
    assert VerificationKind.SOIL_DEVICE.limit is None
    protein = VerificationKind.PROTEIN.limit
    assert protein is not None
    assert protein.contains(3.0)
    assert not protein.contains(3.1)


def test_a_visual_test_needs_a_visual_reading() -> None:
    with pytest.raises(ValidationError):
        Verification(VerificationKind.SOIL_DEVICE, "WD-2", MORNING, "T-4471")
    with pytest.raises(ValidationError):
        Verification(
            VerificationKind.SOIL_DEVICE, "WD-2", MORNING, "T-4471", value=2.0, visual_pass=True
        )


def test_a_measured_test_needs_a_number() -> None:
    with pytest.raises(ValidationError):
        Verification(VerificationKind.ATP, "WD-2", MORNING, "T-4471")
    with pytest.raises(ValidationError):
        Verification(VerificationKind.ATP, "WD-2", MORNING, "T-4471", value=40.0, visual_pass=True)


def test_a_negative_residue_is_refused() -> None:
    with pytest.raises(ValidationError):
        Verification(VerificationKind.PROTEIN, "WD-2", MORNING, "T-4471", value=-1.0)


def test_identifiers_are_normalised() -> None:
    result = Verification(
        VerificationKind.ATP, "wd 2", MORNING, "t 4471", value=40.0, lot="bi 24a17"
    )
    assert result.equipment == "WD-2"
    assert result.by == "T-4471"
    assert result.lot == "BI-24A17"


def test_a_visual_pass_and_fail() -> None:
    assert soil().passed
    assert not soil(passed=False).passed
    assert soil().explain() == "soil device passed on WD-2"
    assert "failed" in soil(passed=False).explain()


def test_a_measured_result_is_judged_against_the_band() -> None:
    good = Verification(VerificationKind.ATP, "WD-2", MORNING, "T-4471", value=40.0)
    bad = Verification(VerificationKind.ATP, "WD-2", MORNING, "T-4471", value=400.0)
    assert good.passed
    assert not bad.passed
    assert "300.0 RLU over" in bad.explain()


def test_the_subject_lands_in_the_explanation() -> None:
    result = Verification(
        VerificationKind.PROTEIN, "WD-2", MORNING, "T-4471", value=1.0, subject="SU-1234"
    )
    assert result.explain().startswith("WD-2 on SU-1234:")


def test_the_log_keeps_results_in_time_order() -> None:
    log = VerificationLog.of([soil(datetime(2024, 5, 2, 7, 0)), soil(MORNING)])
    assert [item.at for item in log.results] == [MORNING, datetime(2024, 5, 2, 7, 0)]


def test_results_are_filtered_by_machine() -> None:
    log = VerificationLog.of([soil(), soil(equipment="WD-3")])
    assert len(log.for_equipment("wd 2")) == 1


def test_a_machine_is_verified_only_by_a_passing_soil_device() -> None:
    log = VerificationLog.of([soil(passed=False)])
    assert not log.verified_on("WD-2", date(2024, 5, 1))
    assert log.with_result(soil()).verified_on("WD-2", date(2024, 5, 1))


def test_an_atp_result_does_not_verify_the_machine_for_the_day() -> None:
    atp = Verification(VerificationKind.ATP, "WD-2", MORNING, "T-4471", value=10.0)
    assert not VerificationLog.of([atp]).verified_on("WD-2", date(2024, 5, 1))


def test_on_day_filters_to_the_day() -> None:
    log = VerificationLog.of([soil(), soil(datetime(2024, 5, 2, 7, 0))])
    assert len(log.on_day("WD-2", date(2024, 5, 1))) == 1


def test_the_suspect_window_runs_back_to_the_last_pass() -> None:
    first = soil(datetime(2024, 5, 1, 7, 0))
    failure = soil(datetime(2024, 5, 3, 7, 0), passed=False)
    log = VerificationLog.of([first, soil(datetime(2024, 5, 2, 7, 0)), failure])
    start, end = log.suspect_window("WD-2", failure)
    assert start == datetime(2024, 5, 2, 7, 0)
    assert end == failure.at


def test_with_no_earlier_pass_the_window_opens_at_the_first_record() -> None:
    first = soil(datetime(2024, 5, 1, 7, 0), passed=False)
    failure = soil(datetime(2024, 5, 3, 7, 0), passed=False)
    log = VerificationLog.of([first, failure])
    start, _ = log.suspect_window("WD-2", failure)
    assert start == first.at


def test_a_machine_with_no_history_at_all_gets_a_point_window() -> None:
    failure = soil(passed=False)
    start, end = VerificationLog().suspect_window("WD-2", failure)
    assert start == end == failure.at


def test_a_passing_test_has_no_suspect_window() -> None:
    with pytest.raises(ValidationError):
        VerificationLog().suspect_window("WD-2", soil())


def test_last_pass_before_ignores_later_results() -> None:
    log = VerificationLog.of([soil(datetime(2024, 5, 1, 7, 0)), soil(datetime(2024, 5, 5, 7, 0))])
    found = log.last_pass_before("WD-2", datetime(2024, 5, 3))
    assert found is not None
    assert found.at == datetime(2024, 5, 1, 7, 0)
    assert VerificationLog().last_pass_before("WD-2", datetime(2024, 5, 3)) is None
