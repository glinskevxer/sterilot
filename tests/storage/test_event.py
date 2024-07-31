from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.settings import Settings
from sterilot.storage.event import (
    Event,
    EventRecord,
    Package,
    Packaging,
    compromised,
)

LOT = LotControlNumber("AC-1", date(2024, 3, 1), 2)
STERILIZED = datetime(2024, 3, 1, 9, 0)
NOW = datetime(2024, 9, 1, 9, 0)


def package(**changes: object) -> Package:
    values: dict[str, object] = {
        "asset": "ort 0114",
        "lot": LOT,
        "packaging": Packaging.SEQUENTIAL_WRAP,
        "sterilized_at": STERILIZED,
    }
    values.update(changes)
    return Package(**values)  # type: ignore[arg-type]


def happened(event: Event, day: int = 5, note: str = "") -> EventRecord:
    return EventRecord(event, datetime(2024, 5, day, 10, 0), "T-4471", note)


def test_packaging_lookup_and_visibility() -> None:
    assert Packaging.named("rigid container") is Packaging.RIGID_CONTAINER
    assert Packaging.POUCH.shows_damage
    assert not Packaging.RIGID_CONTAINER.shows_damage
    with pytest.raises(ValidationError):
        Packaging.named("bag")


def test_event_lookup_and_which_ones_matter() -> None:
    assert Event.named("seal broken") is Event.SEAL_BROKEN
    assert Event.DROPPED.compromises
    assert not Event.MOVED.compromises
    assert not Event.INSPECTED.compromises
    with pytest.raises(ValidationError):
        Event.named("looked at funny")


def test_an_event_cannot_predate_the_cycle() -> None:
    early = EventRecord(Event.MOVED, datetime(2024, 1, 1, 9, 0), "T-4471")
    with pytest.raises(ValidationError):
        package(events=(early,))


def test_a_fresh_package_is_sterile() -> None:
    assert package().sterile(Settings(), NOW)
    assert package().problems(Settings(), NOW) == ()
    assert package().asset == "ORT-0114"


def test_six_months_on_a_closed_shelf_changes_nothing() -> None:
    assert package().sterile(Settings(), datetime(2026, 1, 1, 9, 0))


def test_a_dropped_package_is_compromised_from_that_day() -> None:
    dropped = package().with_event(happened(Event.DROPPED))
    assert not dropped.sterile(Settings(), NOW)
    assert dropped.problems(Settings(), NOW) == ("dropped on 2024-05-05",)


def test_moving_a_package_does_not_compromise_it() -> None:
    moved = package().with_event(happened(Event.MOVED)).with_event(happened(Event.INSPECTED, 6))
    assert moved.sterile(Settings(), NOW)
    assert moved.compromising_events() == ()


def test_several_events_are_all_reported() -> None:
    spoiled = package().with_event(happened(Event.WET)).with_event(happened(Event.TORN, 9))
    assert len(spoiled.problems(Settings(), NOW)) == 2


def test_a_department_running_a_shelf_life_gets_an_expiry() -> None:
    settings = Settings(shelf_life_days=180)
    assert package().expires_on(settings) == date(2024, 8, 28)
    assert package().expires_on(Settings()) is None


def test_an_expired_package_is_named_with_its_date() -> None:
    settings = Settings(shelf_life_days=180)
    problems = package().problems(settings, NOW)
    assert problems == ("the shelf life ran out on 2024-08-28",)


def test_a_package_inside_its_shelf_life_passes() -> None:
    settings = Settings(shelf_life_days=365)
    assert package().sterile(settings, NOW)


def test_a_package_on_its_expiry_day_has_run_out() -> None:
    settings = Settings(shelf_life_days=180)
    assert not package().sterile(settings, datetime(2024, 8, 28, 8, 0))


def test_a_moment_before_the_package_existed_is_refused() -> None:
    with pytest.raises(ValidationError):
        package().problems(Settings(), datetime(2024, 1, 1, 9, 0))


def test_age_is_measured_from_the_cycle() -> None:
    assert package().age(datetime(2024, 3, 2, 9, 0)).days == 1


def test_event_records_describe_themselves() -> None:
    record = happened(Event.DROPPED, note="on the dock")
    assert record.describe() == "2024-05-05 10:00 dropped by T-4471, on the dock"
    assert happened(Event.MOVED).describe().endswith("by T-4471")


def test_compromised_filters_a_shelf() -> None:
    good = package()
    bad = package(asset="ORT-0115").with_event(happened(Event.WET))
    found = compromised([good, bad], Settings(), NOW)
    assert [item.asset for item in found] == ["ORT-0115"]


def test_of_builds_from_an_iterable() -> None:
    made = Package.of("ORT-0114", LOT, Packaging.POUCH, STERILIZED, [happened(Event.MOVED)])
    assert len(made.events) == 1
    assert str(made) == "ORT-0114 AC-1-20240301-02"
