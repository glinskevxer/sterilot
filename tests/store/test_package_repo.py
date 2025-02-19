from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.errors import NotFoundError
from sterilot.ids import LotControlNumber
from sterilot.settings import Settings
from sterilot.storage.event import Event, EventRecord, Package, Packaging
from sterilot.storage.shelf import Location, ParLevel, Zone
from sterilot.store.package_repo import PackageStore
from sterilot.store.store import Store

LOT = LotControlNumber("AC-1", date(2025, 2, 20), 1)
STERILIZED = datetime(2025, 2, 20, 9, 0)
NOW = datetime(2025, 2, 25, 9, 0)


@pytest.fixture
def packages() -> Iterator[PackageStore]:
    store = Store.in_memory()
    yield store.packages
    store.close()


def location(code: str = "ST-A1") -> Location:
    return Location(code, "rack A1", Zone.STERILE_STORE, 24, 30.0, 60.0)


def package(asset: str = "ORT-0114", lot: LotControlNumber = LOT) -> Package:
    return Package(asset, lot, Packaging.SEQUENTIAL_WRAP, STERILIZED)


def test_a_location_round_trips(packages: PackageStore) -> None:
    packages.save_location(location())
    found = packages.location("st a1")
    assert found.capacity_units == 24
    assert found.usable()


def test_an_unusable_location_keeps_its_measurements(packages: PackageStore) -> None:
    packages.save_location(
        Location("ST-B1", "under the sink", Zone.STERILE_STORE, 6, 10.0, 60.0, under_plumbing=True)
    )
    found = packages.location("ST-B1")
    assert not found.usable()
    assert len(found.problems()) == 2


def test_an_unknown_location_is_refused(packages: PackageStore) -> None:
    with pytest.raises(NotFoundError):
        packages.location("ST-Z9")


def test_the_storage_map_carries_locations_and_pars(packages: PackageStore) -> None:
    packages.save_location(location())
    packages.save_par(ParLevel("ORT-MAJOR", 2, 5))
    plan = packages.storage_map()
    assert plan.capacity() == 24
    assert plan.par("ORT-MAJOR") is not None
    assert plan.build_list({"ORT-MAJOR": 1}) == (("ORT-MAJOR", 4),)


def test_a_package_round_trips_with_its_events(packages: PackageStore) -> None:
    packages.save_location(location())
    made = package().with_event(
        EventRecord(Event.MOVED, datetime(2025, 2, 21, 9, 0), "T-4471", "moved to A1")
    )
    packages.shelve(made, "ST-A1", "ORT-MAJOR")
    found = packages.package("ort 0114", LOT)
    assert found.packaging is Packaging.SEQUENTIAL_WRAP
    assert len(found.events) == 1
    assert found.sterile(Settings(), NOW)


def test_an_unknown_package_is_refused(packages: PackageStore) -> None:
    with pytest.raises(NotFoundError):
        packages.package("ORT-0114", LOT)


def test_the_shelf_reads_back_with_the_set_code(packages: PackageStore) -> None:
    packages.save_location(location())
    packages.shelve(package(), "ST-A1", "ort major")
    shelf = packages.shelf()
    assert [item.code for item in shelf] == ["ORT-MAJOR"]
    assert shelf[0].location == "ST-A1"


def test_on_hand_counts_what_is_usable(packages: PackageStore) -> None:
    packages.save_location(location())
    packages.shelve(package("ORT-0114"), "ST-A1", "ORT-MAJOR")
    packages.shelve(package("ORT-0115"), "ST-A1", "ORT-MAJOR")
    assert packages.on_hand(NOW) == {"ORT-MAJOR": 2}


def test_an_event_takes_a_package_out_of_the_count(packages: PackageStore) -> None:
    packages.save_location(location())
    packages.shelve(package(), "ST-A1", "ORT-MAJOR")
    packages.record_event(
        "ORT-0114", LOT, EventRecord(Event.TORN, datetime(2025, 2, 22, 9, 0), "T-4471", "wrap torn")
    )
    assert packages.on_hand(NOW) == {}


def test_picking_takes_the_oldest_first(packages: PackageStore) -> None:
    packages.save_location(location())
    newer = Package(
        "ORT-0115",
        LotControlNumber("AC-1", date(2025, 2, 24), 1),
        Packaging.SEQUENTIAL_WRAP,
        datetime(2025, 2, 24, 9, 0),
    )
    packages.shelve(newer, "ST-A1", "ORT-MAJOR")
    packages.shelve(package("ORT-0114"), "ST-A1", "ORT-MAJOR")
    result = packages.pick("ORT-MAJOR", 1, NOW)
    assert result.assets() == ("ORT-0114",)


def test_a_short_pick_says_so(packages: PackageStore) -> None:
    packages.save_location(location())
    packages.shelve(package(), "ST-A1", "ORT-MAJOR")
    result = packages.pick("ORT-MAJOR", 3, NOW)
    assert result.short == 2


def test_removing_a_package_clears_its_events(packages: PackageStore) -> None:
    packages.save_location(location())
    packages.shelve(package(), "ST-A1", "ORT-MAJOR")
    packages.record_event(
        "ORT-0114", LOT, EventRecord(Event.MOVED, datetime(2025, 2, 22, 9, 0), "T-4471")
    )
    packages.remove(packages.shelf())
    assert packages.shelf() == ()
    with pytest.raises(NotFoundError):
        packages.package("ORT-0114", LOT)
