from __future__ import annotations

from datetime import date

import pytest

from sterilot.decon.washer import Washer, WasherClass
from sterilot.errors import ConflictError, ValidationError
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.quality.log import (
    Duty,
    DutyLog,
    LogEntry,
    duties_for_sterilizer,
    duties_for_washer,
)
from sterilot.sterilizer.equipment import Sterilizer

DAY = date(2024, 10, 2)


def prevac() -> Sterilizer:
    return Sterilizer("AC-1", "Amsco 400", "Steris", frozenset({Method.STEAM_PREVAC}))


def gravity() -> Sterilizer:
    return Sterilizer("AC-2", "Amsco 400", "Steris", frozenset({Method.STEAM_GRAVITY}))


def washer(kind: WasherClass = WasherClass.SINGLE_CHAMBER) -> Washer:
    return Washer("WD-2", "Reliance", "Steris", kind)


def entry(
    day: date = DAY,
    duty: Duty = Duty.AIR_REMOVAL,
    passed: bool = True,
    equipment: str = "ac 1",
    **changes: object,
) -> LogEntry:
    values: dict[str, object] = {
        "day": day,
        "equipment": equipment,
        "duty": duty,
        "passed": passed,
        "by": "t 4471",
    }
    if not passed:
        values["note"] = "pack showed uneven colour"
    values.update(changes)
    return LogEntry(**values)  # type: ignore[arg-type]


def test_duty_lookup() -> None:
    assert Duty.named("air removal") is Duty.AIR_REMOVAL
    assert Duty.CLEANING.label == "cleaning"
    with pytest.raises(ValidationError):
        Duty.named("paperwork")


def test_duties_come_from_the_machine() -> None:
    assert duties_for_sterilizer(prevac()) == frozenset({Duty.AIR_REMOVAL, Duty.BIOLOGICAL})
    assert duties_for_sterilizer(gravity()) == frozenset({Duty.BIOLOGICAL})
    assert duties_for_washer(washer()) == frozenset({Duty.CLEANING})
    assert duties_for_washer(washer(WasherClass.ULTRASONIC)) == frozenset()


def test_an_entry_normalises_and_a_failure_is_written_up() -> None:
    made = entry()
    assert made.equipment == "AC-1"
    assert made.by == "T-4471"
    with pytest.raises(ValidationError):
        LogEntry(DAY, "AC-1", Duty.AIR_REMOVAL, False, "T-4471")


def test_entries_describe_themselves() -> None:
    assert entry().describe() == "2024-10-02 AC-1 air removal pass"
    assert "FAIL, pack showed uneven colour" in entry(passed=False).describe()


def test_the_same_duty_cannot_be_logged_twice_in_a_day() -> None:
    log = DutyLog.of([entry()])
    with pytest.raises(ConflictError):
        log.with_entry(entry())


def test_the_same_duty_on_another_day_is_fine() -> None:
    log = DutyLog.of([entry(), entry(day=date(2024, 10, 3))])
    assert len(log.entries) == 2


def test_covered_needs_every_duty_passed() -> None:
    log = DutyLog.of([entry()])
    duties = duties_for_sterilizer(prevac())
    assert not log.covered("AC-1", DAY, duties)
    log = log.with_entry(entry(duty=Duty.BIOLOGICAL))
    assert log.covered("AC-1", DAY, duties)


def test_a_failed_test_does_not_cover_the_duty() -> None:
    log = DutyLog.of([entry(passed=False), entry(duty=Duty.BIOLOGICAL)])
    assert not log.covered("AC-1", DAY, duties_for_sterilizer(prevac()))


def test_gaps_are_reported_only_for_days_the_machine_ran() -> None:
    log = DutyLog.of([entry()])
    window = DateRange(date(2024, 10, 1), date(2024, 10, 5))
    gaps = log.gaps("AC-1", duties_for_sterilizer(prevac()), window, [DAY])
    assert gaps == ((DAY, Duty.BIOLOGICAL),)


def test_a_day_with_no_entry_at_all_shows_every_duty() -> None:
    window = DateRange(date(2024, 10, 1), date(2024, 10, 5))
    gaps = DutyLog().gaps("AC-1", duties_for_sterilizer(prevac()), window, [DAY])
    assert [duty for _, duty in gaps] == [Duty.AIR_REMOVAL, Duty.BIOLOGICAL]


def test_days_outside_the_window_are_ignored() -> None:
    window = DateRange(date(2024, 10, 1), date(2024, 10, 3))
    gaps = DutyLog().gaps("AC-1", frozenset({Duty.BIOLOGICAL}), window, [date(2024, 10, 9)])
    assert gaps == ()


def test_failures_can_be_listed_by_machine() -> None:
    log = DutyLog.of([entry(passed=False), entry(equipment="AC-2", duty=Duty.BIOLOGICAL)])
    assert len(log.failures()) == 1
    assert log.failures("AC-2") == ()


def test_last_failure_finds_the_most_recent_one() -> None:
    log = DutyLog.of(
        [
            entry(day=date(2024, 10, 1), passed=False),
            entry(day=date(2024, 10, 4), passed=False),
        ]
    )
    found = log.last_failure("AC-1", Duty.AIR_REMOVAL)
    assert found is not None
    assert found.day == date(2024, 10, 4)
    assert log.last_failure("AC-1", Duty.BIOLOGICAL) is None


def test_a_clean_run_counts_back_from_the_day_asked_for() -> None:
    log = DutyLog.of([entry(day=date(2024, 10, day)) for day in (1, 2, 3, 4)])
    assert log.clean_run("AC-1", Duty.AIR_REMOVAL, date(2024, 10, 4)) == 4
    assert log.clean_run("AC-1", Duty.AIR_REMOVAL, date(2024, 10, 5)) == 0


def test_a_failure_breaks_the_run() -> None:
    log = DutyLog.of(
        [
            entry(day=date(2024, 10, 1)),
            entry(day=date(2024, 10, 2), passed=False),
            entry(day=date(2024, 10, 3)),
            entry(day=date(2024, 10, 4)),
        ]
    )
    assert log.clean_run("AC-1", Duty.AIR_REMOVAL, date(2024, 10, 4)) == 2
