from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.cases.preference_card import CardFile, CardLine, PreferenceCard
from sterilot.cases.schedule import Schedule, ScheduledCase
from sterilot.errors import ValidationError
from sterilot.interval import DateRange

DAY = date(2025, 4, 15)


def case(
    number: str = "OR3-01",
    room: str = "OR3",
    hour: int = 8,
    minutes: int = 120,
    card: str = "PC-118",
) -> ScheduledCase:
    return ScheduledCase(
        case=number,
        room=room,
        surgeon="Okonkwo",
        procedure="total knee revision",
        starts_at=datetime(2025, 4, 15, hour, 0),
        minutes=minutes,
        card_reference=card,
    )


def cards() -> CardFile:
    card = PreferenceCard.of(
        "PC-118",
        "Okonkwo",
        "total knee revision",
        [CardLine("ORT-MAJOR", quantity=2), CardLine("GEN-MINOR")],
        DateRange.starting(date(2025, 1, 1)),
    )
    return CardFile().with_card(card)


def test_identifiers_are_normalised() -> None:
    made = case()
    assert made.case == "OR3-01"
    assert made.room == "OR3"
    assert made.card_reference == "PC-118"


def test_a_case_names_a_surgeon_a_procedure_and_takes_time() -> None:
    with pytest.raises(ValidationError):
        ScheduledCase("OR3-01", "OR3", " ", "knee", datetime(2025, 4, 15, 8), 60)
    with pytest.raises(ValidationError):
        ScheduledCase("OR3-01", "OR3", "Okonkwo", "", datetime(2025, 4, 15, 8), 60)
    with pytest.raises(ValidationError):
        ScheduledCase("OR3-01", "OR3", "Okonkwo", "knee", datetime(2025, 4, 15, 8), 0)


def test_a_case_knows_its_window_and_when_the_trays_are_due() -> None:
    made = case()
    assert made.window.minutes == pytest.approx(120.0)
    assert made.ready_by() == datetime(2025, 4, 15, 7, 0)
    assert made.ready_by(lead_minutes=90) == datetime(2025, 4, 15, 6, 30)
    assert made.day == DAY


def test_a_case_describes_itself() -> None:
    assert case().describe() == "08:00 OR3 Okonkwo total knee revision (120 min)"


def test_the_schedule_sorts_by_start_and_room() -> None:
    schedule = Schedule.of([case("OR4-01", "OR4", hour=8), case("OR3-01", "OR3", hour=8)])
    assert [item.room for item in schedule.cases] == ["OR3", "OR4"]


def test_cases_are_filtered_by_day_and_room() -> None:
    schedule = Schedule.of([case("OR3-01"), case("OR4-01", "OR4")])
    assert len(schedule.on_day(DAY)) == 2
    assert schedule.on_day(date(2025, 4, 16)) == ()
    assert [item.case for item in schedule.in_room("or3")] == ["OR3-01"]
    assert schedule.in_room("OR3", date(2025, 4, 16)) == ()


def test_rooms_are_listed_for_a_day() -> None:
    schedule = Schedule.of([case("OR3-01"), case("OR4-01", "OR4")])
    assert schedule.rooms(DAY) == ("OR3", "OR4")


def test_two_cases_in_one_room_at_one_time_are_reported() -> None:
    schedule = Schedule.of([case("OR3-01", hour=8), case("OR3-02", hour=9)])
    overlaps = schedule.overlaps(DAY)
    assert len(overlaps) == 1
    assert overlaps[0][0].case == "OR3-01"


def test_cases_that_do_not_overlap_are_not_reported() -> None:
    schedule = Schedule.of([case("OR3-01", hour=8, minutes=60), case("OR3-02", hour=9)])
    assert schedule.overlaps(DAY) == ()


def test_two_rooms_at_once_is_not_an_overlap() -> None:
    schedule = Schedule.of([case("OR3-01"), case("OR4-01", "OR4")])
    assert schedule.overlaps(DAY) == ()


def test_the_day_demand_adds_up_the_cards() -> None:
    schedule = Schedule.of([case("OR3-01"), case("OR4-01", "OR4")])
    assert schedule.demand(cards(), DAY) == {"ORT-MAJOR": 4, "GEN-MINOR": 2}


def test_a_case_with_no_card_demands_nothing_and_is_listed() -> None:
    schedule = Schedule.of([case("OR3-01", card="")])
    assert schedule.demand(cards(), DAY) == {}
    assert [item.case for item in schedule.unattached(DAY)] == ["OR3-01"]


def test_a_card_that_is_not_in_force_is_skipped() -> None:
    schedule = Schedule.of([case("OR3-01", card="PC-999")])
    assert schedule.demand(cards(), DAY) == {}


def test_the_first_start_of_the_day() -> None:
    schedule = Schedule.of([case("OR3-01", hour=10), case("OR4-01", "OR4", hour=7)])
    assert schedule.first_start(DAY) == datetime(2025, 4, 15, 7, 0)
    assert schedule.first_start(date(2025, 4, 16)) is None


def test_adding_a_case_keeps_the_order() -> None:
    schedule = Schedule.of([case("OR3-01", hour=10)])
    grown = schedule.with_case(case("OR4-01", "OR4", hour=7))
    assert [item.case for item in grown.cases] == ["OR4-01", "OR3-01"]
    assert len(schedule.cases) == 1
