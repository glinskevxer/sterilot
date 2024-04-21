from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.assets.loaner import LoanerSet, LoanerStage
from sterilot.errors import ValidationError

CASE_START = datetime(2024, 5, 2, 7, 30)


def loaner(**changes: object) -> LoanerSet:
    values: dict[str, object] = {
        "reference": "ln 44",
        "vendor": "Medline Ortho",
        "set_name": "revision knee tray 2",
        "case": "or3 20240502 01",
        "case_start": CASE_START,
        "expected_at": datetime(2024, 4, 30, 10, 0),
    }
    values.update(changes)
    return LoanerSet(**values)  # type: ignore[arg-type]


def arrived(hours_before: float = 48.0, **changes: object) -> LoanerSet:
    received = CASE_START - __import__("datetime").timedelta(hours=hours_before)
    values: dict[str, object] = {
        "received_at": received,
        "counted_at": received,
        "rep_present_at_count": True,
        "piece_count": 214,
        "reprocessed_at": received,
    }
    values.update(changes)
    return loaner(**values)


def test_stage_lookup() -> None:
    assert LoanerStage.named("RETURNED") is LoanerStage.RETURNED
    with pytest.raises(ValidationError):
        LoanerStage.named("posted")


def test_reference_and_case_are_normalised() -> None:
    item = loaner()
    assert item.reference == "LN-44"
    assert item.case == "OR3-20240502-01"


def test_vendor_and_set_name_are_required() -> None:
    with pytest.raises(ValidationError):
        loaner(vendor=" ")
    with pytest.raises(ValidationError):
        loaner(set_name="")


def test_a_loaner_cannot_be_expected_after_the_case() -> None:
    with pytest.raises(ValidationError):
        loaner(expected_at=datetime(2024, 5, 2, 9, 0))


def test_a_counted_set_has_pieces() -> None:
    with pytest.raises(ValidationError):
        loaner(piece_count=0)


def test_milestones_have_to_run_in_order() -> None:
    with pytest.raises(ValidationError):
        loaner(
            received_at=datetime(2024, 5, 1, 10, 0),
            counted_at=datetime(2024, 4, 30, 10, 0),
        )


def test_stage_reads_the_furthest_milestone() -> None:
    assert loaner().stage is LoanerStage.EXPECTED
    assert arrived().stage is LoanerStage.REPROCESSED
    assert arrived(released_at=CASE_START).stage is LoanerStage.RELEASED
    assert (
        arrived(released_at=CASE_START, returned_at=datetime(2024, 5, 3, 9, 0)).stage
        is LoanerStage.RETURNED
    )


def test_lead_time_is_measured_to_the_case() -> None:
    assert loaner().lead_time() is None
    assert arrived(hours_before=50).lead_time() is not None
    lead = arrived(hours_before=50).lead_time()
    assert lead is not None
    assert lead.hours == pytest.approx(50.0)


def test_a_set_arriving_after_the_case_starts_reads_zero_lead() -> None:
    late = loaner(received_at=datetime(2024, 5, 2, 9, 0))
    lead = late.lead_time()
    assert lead is not None
    assert lead.hours == pytest.approx(0.0)


def test_the_deadline_is_the_case_less_the_window() -> None:
    assert loaner().deadline(48) == datetime(2024, 4, 30, 7, 30)


def test_a_set_that_has_not_arrived_reports_only_that() -> None:
    assert loaner().problems(48) == ("the set has not arrived",)


def test_a_late_set_is_named_as_late() -> None:
    problems = arrived(hours_before=6).problems(48)
    assert problems == ("the set arrived inside the 48 hour window",)


def test_an_uncounted_set_is_not_ready() -> None:
    problems = arrived(counted_at=None).problems(48)
    assert "the set has not been counted in" in problems


def test_a_count_without_the_rep_is_a_problem() -> None:
    problems = arrived(rep_present_at_count=False).problems(48)
    assert "the count was taken without the vendor representative" in problems


def test_a_set_that_was_never_reprocessed_is_not_ready() -> None:
    problems = arrived(reprocessed_at=None).problems(48)
    assert "the set has not been reprocessed here" in problems


def test_a_missing_piece_count_is_a_problem() -> None:
    assert "no piece count was recorded" in arrived(piece_count=None).problems(48)


def test_a_clean_loaner_is_ready() -> None:
    assert arrived().ready_for_case(48)
    assert arrived().problems(48) == ()


def test_a_set_cannot_go_back_before_it_was_released() -> None:
    assert arrived().may_return() == "the set has not been released to the case"


def test_a_set_cannot_go_back_soiled() -> None:
    item = arrived(released_at=CASE_START)
    assert item.may_return() == "the set has to be decontaminated after the case"


def test_a_set_decontaminated_after_the_case_may_go_back() -> None:
    item = arrived(released_at=CASE_START, decontaminated_at=datetime(2024, 5, 2, 14, 0))
    assert item.may_return() is None


def test_label() -> None:
    assert str(loaner()) == "LN-44 revision knee tray 2 for OR3-20240502-01"
