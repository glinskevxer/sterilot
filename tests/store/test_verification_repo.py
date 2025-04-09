from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.decon.verification import Verification, VerificationKind
from sterilot.errors import ValidationError
from sterilot.store.store import Store
from sterilot.store.verification_repo import VerificationStore

DAY = date(2025, 4, 10)


@pytest.fixture
def checks() -> Iterator[VerificationStore]:
    store = Store.in_memory()
    yield store.verifications
    store.close()


def soil(at: datetime, passed: bool = True, equipment: str = "WD-2") -> Verification:
    return Verification(VerificationKind.SOIL_DEVICE, equipment, at, "T-4471", visual_pass=passed)


def test_a_soil_result_round_trips(checks: VerificationStore) -> None:
    checks.save(soil(datetime(2025, 4, 10, 6, 40)))
    found = checks.for_equipment("wd 2")
    assert len(found) == 1
    assert found[0].passed
    assert checks.verified_on("WD-2", DAY)


def test_a_measured_result_round_trips(checks: VerificationStore) -> None:
    checks.save(
        Verification(
            VerificationKind.ATP,
            "WD-2",
            datetime(2025, 4, 10, 7, 0),
            "T-4471",
            value=40.0,
            subject="SU-1234",
        )
    )
    found = checks.on_day("WD-2", DAY)
    assert found[0].value == pytest.approx(40.0)
    assert found[0].subject == "SU-1234"
    assert not checks.verified_on("WD-2", DAY)


def test_a_result_in_the_last_second_of_the_day_is_still_found(checks: VerificationStore) -> None:
    checks.save(soil(datetime(2025, 4, 10, 23, 59, 59)))
    assert len(checks.on_day("WD-2", DAY)) == 1


def test_results_are_kept_apart_by_machine(checks: VerificationStore) -> None:
    checks.save(soil(datetime(2025, 4, 10, 6, 40)))
    checks.save(soil(datetime(2025, 4, 10, 6, 45), equipment="WD-3"))
    assert len(checks.for_equipment("WD-2")) == 1
    assert len(checks.log().results) == 2


def test_the_suspect_window_runs_back_to_the_last_pass(checks: VerificationStore) -> None:
    checks.save(soil(datetime(2025, 4, 9, 6, 40)))
    checks.save(soil(datetime(2025, 4, 10, 6, 40), passed=False))
    start, end = checks.suspect_window("WD-2", datetime(2025, 4, 10, 6, 40))
    assert start == datetime(2025, 4, 9, 6, 40)
    assert end == datetime(2025, 4, 10, 6, 40)


def test_a_moment_with_no_failure_is_refused(checks: VerificationStore) -> None:
    checks.save(soil(datetime(2025, 4, 10, 6, 40)))
    with pytest.raises(ValidationError):
        checks.suspect_window("WD-2", datetime(2025, 4, 10, 6, 40))
