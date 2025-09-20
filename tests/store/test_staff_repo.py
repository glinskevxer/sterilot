from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from sterilot.interval import DateRange
from sterilot.staff.tech import Certification, Role, Technician
from sterilot.store.staff_repo import StaffStore
from sterilot.store.store import Store

DAY = date(2025, 9, 17)


@pytest.fixture
def staff() -> Iterator[StaffStore]:
    store = Store.in_memory()
    yield store.staff
    store.close()


def test_an_employment_window_round_trips(staff: StaffStore) -> None:
    staff.save(
        Technician(
            "T-4471",
            "R Ferreira",
            Role.TECHNICIAN,
            employed=DateRange(date(2019, 1, 1), date(2025, 6, 1)),
        )
    )
    found = staff.get("T-4471")
    assert found.employed is not None
    assert not found.employed_on(DAY)


def test_a_person_with_no_window_is_always_employed(staff: StaffStore) -> None:
    staff.save(Technician("T-4471", "R Ferreira", Role.TECHNICIAN))
    found = staff.get("T-4471")
    assert found.employed is None
    assert found.employed_on(DAY)


def test_a_certification_round_trips(staff: StaffStore) -> None:
    person = Technician("T-4471", "R Ferreira", Role.TECHNICIAN).with_certification(
        Certification("HSPA", "CRCST-1", DateRange(date(2023, 1, 1), date(2030, 1, 1)))
    )
    staff.save(person)
    found = staff.get("T-4471")
    assert found.certified_on(DAY)
    assert found.certifications[0].body == "HSPA"


def test_the_roster_knows_who_it_holds(staff: StaffStore) -> None:
    staff.save(Technician("T-4471", "R Ferreira", Role.TECHNICIAN))
    assert staff.exists("t 4471")
    assert not staff.exists("T-9999")
    assert [person.badge for person in staff.roster().people] == ["T-4471"]
