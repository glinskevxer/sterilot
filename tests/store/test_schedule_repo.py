from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.cases.preference_card import CardLine, PreferenceCard
from sterilot.cases.schedule import ScheduledCase
from sterilot.errors import NotFoundError
from sterilot.interval import DateRange
from sterilot.store.schedule_repo import ScheduleStore
from sterilot.store.store import Store

DAY = date(2025, 4, 16)


@pytest.fixture
def schedule() -> Iterator[ScheduleStore]:
    store = Store.in_memory()
    yield store.schedule
    store.close()


def case(number: str = "OR3-01", room: str = "OR3", hour: int = 8) -> ScheduledCase:
    return ScheduledCase(
        case=number,
        room=room,
        surgeon="Okonkwo",
        procedure="total knee revision",
        starts_at=datetime(2025, 4, 16, hour, 0),
        minutes=120,
        card_reference="PC-118",
    )


def card(revision: int = 1, start: date = date(2025, 1, 1), quantity: int = 2) -> PreferenceCard:
    return PreferenceCard.of(
        "PC-118",
        "Okonkwo",
        "total knee revision",
        [CardLine("ORT-MAJOR", quantity=quantity), CardLine("GEN-MINOR", essential=False)],
        DateRange.starting(start),
        revision=revision,
        loaner_sets=("revision knee tray 2",),
    )


def test_a_case_round_trips(schedule: ScheduleStore) -> None:
    schedule.save_case(case())
    found = schedule.case("or3 01")
    assert found.room == "OR3"
    assert found.minutes == 120
    assert found.card_reference == "PC-118"


def test_an_unknown_case_is_refused(schedule: ScheduleStore) -> None:
    with pytest.raises(NotFoundError):
        schedule.case("OR9-99")


def test_the_day_comes_back_as_a_schedule(schedule: ScheduleStore) -> None:
    schedule.save_case(case("OR4-01", "OR4", hour=7))
    schedule.save_case(case("OR3-01", "OR3", hour=8))
    found = schedule.schedule(DAY)
    assert [item.case for item in found.cases] == ["OR4-01", "OR3-01"]
    assert found.rooms(DAY) == ("OR3", "OR4")


def test_a_case_on_another_day_is_not_in_the_schedule(schedule: ScheduleStore) -> None:
    schedule.save_case(case())
    assert schedule.schedule(date(2025, 4, 17)).cases == ()


def test_a_card_round_trips_with_its_lines(schedule: ScheduleStore) -> None:
    schedule.save_card(card())
    found = schedule.card("pc 118", DAY)
    assert found.wanted() == {"ORT-MAJOR": 2, "GEN-MINOR": 1}
    assert found.needs_loaner
    assert found.line_for("GEN-MINOR").essential is False


def test_a_card_not_in_force_is_refused(schedule: ScheduleStore) -> None:
    schedule.save_card(card(start=date(2026, 1, 1)))
    with pytest.raises(NotFoundError):
        schedule.card("PC-118", DAY)


def test_revising_closes_the_previous_revision(schedule: ScheduleStore) -> None:
    schedule.save_card(card())
    schedule.revise_card(card(revision=2, start=date(2025, 4, 1), quantity=3))
    assert schedule.card("PC-118", date(2025, 3, 1)).revision == 1
    assert schedule.card("PC-118", DAY).revision == 2
    assert schedule.card("PC-118", DAY).wanted()["ORT-MAJOR"] == 3


def test_the_card_file_reads_every_revision(schedule: ScheduleStore) -> None:
    schedule.save_card(card())
    schedule.revise_card(card(revision=2, start=date(2025, 4, 1)))
    file = schedule.cards()
    assert len(file.cards) == 2
    assert file.for_reference("PC-118", DAY).revision == 2


def test_the_demand_of_a_day_comes_from_the_cards(schedule: ScheduleStore) -> None:
    schedule.save_card(card())
    schedule.save_case(case("OR3-01"))
    schedule.save_case(case("OR4-01", "OR4"))
    demand = schedule.schedule(DAY).demand(schedule.cards(), DAY)
    assert demand == {"ORT-MAJOR": 4, "GEN-MINOR": 2}
