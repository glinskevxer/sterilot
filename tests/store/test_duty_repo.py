from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from sterilot.errors import NotFoundError
from sterilot.quality.log import Duty, LogEntry
from sterilot.store.duty_repo import DutyStore
from sterilot.store.store import Store

DAY = date(2025, 9, 17)


@pytest.fixture
def duties() -> Iterator[DutyStore]:
    store = Store.in_memory()
    yield store.duties
    store.close()


def test_a_duty_that_was_never_logged_is_refused(duties: DutyStore) -> None:
    with pytest.raises(NotFoundError) as caught:
        duties.get("AC-1", DAY, Duty.AIR_REMOVAL)
    assert caught.value.context["equipment"] == "AC-1"


def test_a_logged_duty_comes_back(duties: DutyStore) -> None:
    duties.save(LogEntry(DAY, "AC-1", Duty.AIR_REMOVAL, True, "T-4471"))
    assert duties.get("ac 1", DAY, Duty.AIR_REMOVAL).passed


def test_saving_the_same_duty_again_replaces_it(duties: DutyStore) -> None:
    duties.save(LogEntry(DAY, "AC-1", Duty.AIR_REMOVAL, True, "T-4471"))
    duties.save(LogEntry(DAY, "AC-1", Duty.AIR_REMOVAL, False, "T-4471", "uneven"))
    found = duties.get("AC-1", DAY, Duty.AIR_REMOVAL)
    assert not found.passed
    assert found.note == "uneven"
    assert len(duties.on_day("AC-1", DAY)) == 1
