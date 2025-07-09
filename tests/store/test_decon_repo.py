from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.decon.manual import ManualClean, PointOfUse
from sterilot.errors import NotFoundError
from sterilot.store.decon_repo import DeconStore
from sterilot.store.store import Store
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

CASE_END = datetime(2025, 7, 1, 11, 0)
DAY = date(2025, 7, 1)


@pytest.fixture
def decon() -> Iterator[DeconStore]:
    store = Store.in_memory()
    yield store.decon
    store.close()


def trip(**changes: object) -> PointOfUse:
    values: dict[str, object] = {
        "case": "OR3-01",
        "finished_at": CASE_END,
        "collected_at": datetime(2025, 7, 1, 11, 40),
    }
    values.update(changes)
    return PointOfUse(**values)  # type: ignore[arg-type]


def clean(**changes: object) -> ManualClean:
    values: dict[str, object] = {
        "catalog": "SU-9001",
        "at": datetime(2025, 7, 1, 12, 15),
        "by": "T-4471",
        "soaked": Duration.of_minutes(4),
        "detergent_temperature": Temperature(35.0),
        "brush_mm": 4.0,
        "brush_passes": 3,
    }
    values.update(changes)
    return ManualClean(**values)  # type: ignore[arg-type]


def test_a_trip_round_trips(decon: DeconStore) -> None:
    decon.save_trip(trip())
    found = decon.trip("or3 01")
    assert found.delay.minutes == pytest.approx(40.0)
    assert found.problems() == ()


def test_a_bad_trip_keeps_its_flags(decon: DeconStore) -> None:
    decon.save_trip(trip(kept_moist=False, container_closed=False))
    found = decon.trip("OR3-01")
    assert not found.kept_moist
    assert not found.container_closed
    assert len(found.problems()) == 2


def test_an_unknown_case_is_refused(decon: DeconStore) -> None:
    with pytest.raises(NotFoundError):
        decon.trip("OR9-99")


def test_trips_are_listed_for_a_day(decon: DeconStore) -> None:
    decon.save_trip(trip())
    decon.save_trip(trip(case="OR4-01"))
    assert len(decon.trips_on(DAY)) == 2
    assert decon.trips_on(date(2025, 7, 2)) == ()


def test_only_the_bad_trips_come_back_as_delayed(decon: DeconStore) -> None:
    decon.save_trip(trip())
    decon.save_trip(trip(case="OR4-01", collected_at=datetime(2025, 7, 1, 16, 0)))
    found = decon.delayed_trips(DAY)
    assert [item.case for item in found] == ["OR4-01"]


def test_the_latest_trip_for_a_case_wins(decon: DeconStore) -> None:
    decon.save_trip(trip())
    decon.save_trip(
        trip(finished_at=datetime(2025, 7, 1, 15, 0), collected_at=datetime(2025, 7, 1, 15, 10))
    )
    assert decon.trip("OR3-01").finished_at == datetime(2025, 7, 1, 15, 0)


def test_a_sink_record_round_trips(decon: DeconStore) -> None:
    decon.save_clean(clean(), case="OR3-01")
    found = decon.clean("su 9001", datetime(2025, 7, 1, 12, 15))
    assert found.brush_mm == pytest.approx(4.0)
    assert found.brush_passes == 3
    assert found.soaked.minutes == pytest.approx(4.0)


def test_a_record_with_no_brush_comes_back_without_one(decon: DeconStore) -> None:
    decon.save_clean(clean(brush_mm=None, brush_passes=0))
    found = decon.clean("SU-9001", datetime(2025, 7, 1, 12, 15))
    assert found.brush_mm is None


def test_an_unknown_sink_record_is_refused(decon: DeconStore) -> None:
    with pytest.raises(NotFoundError):
        decon.clean("SU-9001", datetime(2025, 7, 1, 12, 15))


def test_sink_records_are_found_by_case_and_by_item(decon: DeconStore) -> None:
    decon.save_clean(clean(), case="OR3-01")
    decon.save_clean(clean(catalog="SU-1234", brush_mm=None), case="OR4-01")
    assert [item.catalog for item in decon.cleans_for_case("OR3-01")] == ["SU-9001"]
    assert len(decon.cleans_of("SU-1234")) == 1
    assert decon.cleans_for_case("OR9-99") == ()
