from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

from sterilot.assets.loaner import LoanerSet, LoanerStage
from sterilot.errors import NotFoundError
from sterilot.store.loaner_repo import LoanerStore
from sterilot.store.store import Store

CASE_START = datetime(2025, 3, 4, 7, 30)


@pytest.fixture
def loaners() -> Iterator[LoanerStore]:
    store = Store.in_memory()
    yield store.loaners
    store.close()


def loaner(reference: str = "LN-44", **changes: object) -> LoanerSet:
    values: dict[str, object] = {
        "reference": reference,
        "vendor": "Medline Ortho",
        "set_name": "revision knee tray 2",
        "case": "OR3-20250304-01",
        "case_start": CASE_START,
        "expected_at": CASE_START - timedelta(days=2),
    }
    values.update(changes)
    return LoanerSet(**values)  # type: ignore[arg-type]


def arrived(reference: str = "LN-44", hours: float = 48.0, **changes: object) -> LoanerSet:
    received = CASE_START - timedelta(hours=hours)
    values: dict[str, object] = {
        "received_at": received,
        "counted_at": received,
        "rep_present_at_count": True,
        "piece_count": 214,
        "reprocessed_at": received,
    }
    values.update(changes)
    return loaner(reference, **values)


def test_a_loaner_round_trips(loaners: LoanerStore) -> None:
    loaners.save(arrived())
    found = loaners.get("ln 44")
    assert found.vendor == "Medline Ortho"
    assert found.piece_count == 214
    assert found.rep_present_at_count
    assert found.stage is LoanerStage.REPROCESSED


def test_an_expected_loaner_keeps_its_empty_milestones(loaners: LoanerStore) -> None:
    loaners.save(loaner())
    found = loaners.get("LN-44")
    assert found.received_at is None
    assert found.stage is LoanerStage.EXPECTED


def test_an_unknown_reference_is_refused(loaners: LoanerStore) -> None:
    with pytest.raises(NotFoundError):
        loaners.get("LN-99")
    assert not loaners.exists("LN-99")


def test_loaners_are_found_by_case(loaners: LoanerStore) -> None:
    loaners.save(loaner("LN-44"))
    loaners.save(loaner("LN-45", case="OR4-20250304-02"))
    assert [item.reference for item in loaners.for_case("OR3-20250304-01")] == ["LN-44"]


def test_loaners_are_found_by_the_day_of_the_case(loaners: LoanerStore) -> None:
    loaners.save(loaner("LN-44"))
    loaners.save(
        loaner(
            "LN-45",
            case_start=datetime(2025, 3, 5, 7, 30),
            expected_at=datetime(2025, 3, 3, 7, 30),
        )
    )
    assert [item.reference for item in loaners.expected_on(date(2025, 3, 4))] == ["LN-44"]


def test_outstanding_leaves_out_what_went_back(loaners: LoanerStore) -> None:
    loaners.save(arrived("LN-44"))
    loaners.save(
        arrived(
            "LN-45",
            released_at=CASE_START,
            decontaminated_at=CASE_START + timedelta(hours=6),
            returned_at=CASE_START + timedelta(hours=8),
        )
    )
    assert [item.reference for item in loaners.outstanding()] == ["LN-44"]


def test_a_ready_loaner_is_not_listed_as_a_problem(loaners: LoanerStore) -> None:
    loaners.save(arrived())
    assert loaners.not_ready(date(2025, 3, 4), 48) == ()


def test_a_late_loaner_is_listed_with_its_problems(loaners: LoanerStore) -> None:
    loaners.save(arrived(hours=6))
    found = loaners.not_ready(date(2025, 3, 4), 48)
    assert len(found) == 1
    assert "inside the 48 hour window" in found[0][1][0]


def test_a_loaner_that_has_gone_back_is_not_chased(loaners: LoanerStore) -> None:
    loaners.save(
        arrived(
            hours=6,
            released_at=CASE_START,
            decontaminated_at=CASE_START + timedelta(hours=6),
            returned_at=CASE_START + timedelta(hours=8),
        )
    )
    assert loaners.not_ready(date(2025, 3, 4), 48) == ()
