from __future__ import annotations

from datetime import date

import pytest

from sterilot.errors import ValidationError
from sterilot.staff.competency import Competency, CompetencyFile, Task

DAY = date(2024, 9, 10)


def entry(**changes: object) -> Competency:
    values: dict[str, object] = {
        "badge": "t 4471",
        "task": Task.ASSEMBLY,
        "assessed_on": date(2024, 3, 1),
        "assessor": "t 9002",
    }
    values.update(changes)
    return Competency(**values)  # type: ignore[arg-type]


def test_task_lookup_and_risk() -> None:
    assert Task.named("manual clean") is Task.MANUAL_CLEAN
    assert Task.RELEASE.high_risk
    assert not Task.ASSEMBLY.high_risk
    with pytest.raises(ValidationError):
        Task.named("tidying")


def test_badges_are_normalised() -> None:
    made = entry()
    assert made.badge == "T-4471"
    assert made.assessor == "T-9002"


def test_nobody_assesses_themselves() -> None:
    with pytest.raises(ValidationError):
        entry(assessor="T-4471")


def test_an_assessment_observes_the_work() -> None:
    with pytest.raises(ValidationError):
        entry(observations=0)


def test_a_high_risk_task_is_observed_three_times() -> None:
    with pytest.raises(ValidationError):
        entry(task=Task.RELEASE, observations=1)
    signed = Competency("T-4471", Task.RELEASE, date(2024, 3, 1), "T-9002", observations=3)
    assert signed.observations == 3


def test_a_competency_lasts_a_year_by_default() -> None:
    made = entry()
    assert made.current_on(DAY)
    assert not made.current_on(date(2025, 6, 1))
    assert made.days_left(DAY) == 172


def test_an_explicit_end_is_honoured() -> None:
    made = entry(valid_until=date(2024, 8, 1))
    assert not made.current_on(DAY)


def test_an_end_before_the_assessment_is_refused() -> None:
    with pytest.raises(ValidationError):
        entry(valid_until=date(2024, 3, 1))


def test_the_file_answers_who_holds_what() -> None:
    file = CompetencyFile.of([entry()])
    assert file.holds("t 4471", Task.ASSEMBLY, DAY)
    assert not file.holds("T-4471", Task.RELEASE, DAY)
    assert not file.holds("T-9999", Task.ASSEMBLY, DAY)


def test_the_latest_assessment_is_the_one_that_counts() -> None:
    file = CompetencyFile.of([entry(), entry(assessed_on=date(2024, 6, 1), observations=2)])
    current = file.current("T-4471", Task.ASSEMBLY, DAY)
    assert current is not None
    assert current.assessed_on == date(2024, 6, 1)


def test_a_badge_never_assessed_is_named() -> None:
    file = CompetencyFile()
    assert file.refusal("t 4471", Task.RELEASE, DAY) == (
        "T-4471 has never been assessed on release"
    )


def test_a_lapsed_competency_names_the_day_it_ran_out() -> None:
    file = CompetencyFile.of([entry(assessed_on=date(2022, 1, 1))])
    assert file.refusal("T-4471", Task.ASSEMBLY, DAY) == "T-4471 lapsed on assembly on 2023-01-01"


def test_a_current_competency_has_no_refusal() -> None:
    file = CompetencyFile.of([entry()])
    assert file.refusal("T-4471", Task.ASSEMBLY, DAY) is None


def test_an_assessor_has_to_hold_the_competency() -> None:
    file = CompetencyFile.of([entry(badge="T-9002", assessor="T-9100")])
    assert file.valid_assessor("T-9002", Task.ASSEMBLY, DAY)
    assert not file.valid_assessor("T-4471", Task.ASSEMBLY, DAY)


def test_due_within_finds_the_ones_running_out() -> None:
    soon = entry(badge="T-5000", assessed_on=date(2023, 10, 1))
    later = entry(badge="T-6000", assessed_on=date(2024, 8, 1))
    file = CompetencyFile.of([soon, later])
    assert [item.badge for item in file.due_within(DAY, 30)] == ["T-5000"]
    assert file.due_within(DAY, 5) == ()


def test_due_within_looks_only_at_the_latest_assessment() -> None:
    old = entry(badge="T-5000", assessed_on=date(2023, 10, 1))
    fresh = entry(badge="T-5000", assessed_on=date(2024, 9, 1))
    file = CompetencyFile.of([old, fresh])
    assert file.due_within(DAY, 30) == ()


def test_due_within_refuses_a_negative_horizon() -> None:
    with pytest.raises(ValidationError):
        CompetencyFile().due_within(DAY, -1)


def test_entries_are_filtered_by_badge() -> None:
    file = CompetencyFile.of([entry(), entry(badge="T-5000")])
    assert len(file.for_badge("T-4471")) == 1


def test_describe_reads_like_the_form() -> None:
    assert entry().describe() == "T-4471 assembly assessed 2024-03-01 by T-9002"
