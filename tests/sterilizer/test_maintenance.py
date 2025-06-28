from __future__ import annotations

from datetime import date

import pytest

from sterilot.errors import ValidationError
from sterilot.sterilizer.maintenance import Plan, Task

DAY = date(2025, 6, 26)


def task(**changes: object) -> Task:
    values: dict[str, object] = {
        "code": "pm 1",
        "equipment": "ac 1",
        "description": "door gasket",
        "every_days": 180,
        "last_done": date(2025, 1, 1),
    }
    values.update(changes)
    return Task(**values)  # type: ignore[arg-type]


def test_identifiers_are_normalised_and_details_required() -> None:
    made = task()
    assert made.code == "PM-1"
    assert made.equipment == "AC-1"
    with pytest.raises(ValidationError):
        task(description=" ")


def test_a_task_needs_an_interval() -> None:
    with pytest.raises(ValidationError):
        task(every_days=None, every_cycles=None)
    with pytest.raises(ValidationError):
        task(every_days=0)
    with pytest.raises(ValidationError):
        task(every_cycles=0)


def test_a_negative_cycle_count_is_refused() -> None:
    with pytest.raises(ValidationError):
        task(cycles_since=-1)


def test_a_task_never_done_is_always_due() -> None:
    made = task(last_done=None)
    assert made.never_done
    assert made.due(DAY)
    assert made.reason(DAY) == "never done"


def test_a_calendar_task_falls_due_on_its_date() -> None:
    made = task(every_days=180, last_done=date(2025, 1, 1))
    assert made.due_on() == date(2025, 6, 30)
    assert not made.due(DAY)
    assert made.due(date(2025, 6, 30))
    assert made.reason(date(2025, 6, 30)) == "due 2025-06-30"


def test_an_overdue_calendar_task_counts_the_days() -> None:
    made = task(every_days=180, last_done=date(2025, 1, 1))
    assert made.reason(date(2025, 7, 5)) == "5 days overdue"


def test_a_cycle_task_falls_due_on_its_count() -> None:
    made = task(every_days=None, every_cycles=100, cycles_since=99)
    assert made.cycles_left() == 1
    assert not made.due(DAY)
    assert made.after_cycle().due(DAY)
    assert made.after_cycle().reason(DAY) == "cycle interval reached"


def test_a_cycle_task_past_its_interval_says_how_far() -> None:
    made = task(every_days=None, every_cycles=100, cycles_since=104)
    assert made.reason(DAY) == "4 cycles past the interval"


def test_whichever_comes_first_wins() -> None:
    made = task(every_days=365, every_cycles=50, cycles_since=50)
    assert made.due(DAY)
    assert made.due_on() == date(2026, 1, 1)


def test_doing_a_task_resets_both_counters() -> None:
    made = task(every_days=180, every_cycles=100, cycles_since=90).done(DAY)
    assert made.last_done == DAY
    assert made.cycles_since == 0
    assert not made.due(DAY)


def test_a_task_describes_its_interval() -> None:
    assert task().describe() == "PM-1 door gasket every 180 days"
    assert task(every_cycles=100).describe() == "PM-1 door gasket every 180 days or 100 cycles"


def test_a_plan_sorts_by_machine_then_code() -> None:
    plan = Plan.of([task(code="PM-2"), task(code="PM-1", equipment="AC-2"), task(code="PM-1")])
    assert [(item.equipment, item.code) for item in plan.tasks] == [
        ("AC-1", "PM-1"),
        ("AC-1", "PM-2"),
        ("AC-2", "PM-1"),
    ]


def test_a_plan_filters_by_machine() -> None:
    plan = Plan.of([task(), task(code="PM-2", equipment="AC-2")])
    assert [item.code for item in plan.for_equipment("ac 1")] == ["PM-1"]


def test_a_plan_lists_what_is_due() -> None:
    plan = Plan.of([task(), task(code="PM-2", last_done=None)])
    assert [item.code for item in plan.due(DAY)] == ["PM-2"]


def test_a_plan_looks_ahead_without_repeating_what_is_due() -> None:
    plan = Plan.of([task(), task(code="PM-2", last_done=None)])
    coming = plan.coming(DAY, 30)
    assert [item.code for item in coming] == ["PM-1"]
    assert plan.coming(DAY, 1) == ()


def test_looking_back_is_refused() -> None:
    with pytest.raises(ValidationError):
        Plan.of([task()]).coming(DAY, -1)
