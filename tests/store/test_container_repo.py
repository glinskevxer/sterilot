from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from sterilot.assets.container import Container, FilterType
from sterilot.errors import NotFoundError
from sterilot.interval import DateRange
from sterilot.methods import Method
from sterilot.store.container_repo import ContainerStore
from sterilot.store.store import Store

DAY = date(2025, 5, 8)


@pytest.fixture
def containers() -> Iterator[ContainerStore]:
    store = Store.in_memory()
    yield store.containers
    store.close()


def container(asset: str = "RC-2001", **changes: object) -> Container:
    values: dict[str, object] = {
        "asset": asset,
        "model": "Genesis 23x11",
        "manufacturer": "Aesculap",
        "filter_type": FilterType.SYNTHETIC,
        "last_inspection": date(2025, 4, 1),
    }
    values.update(changes)
    return Container(**values)  # type: ignore[arg-type]


def test_a_container_round_trips(containers: ContainerStore) -> None:
    containers.save(container())
    found = containers.get("rc 2001")
    assert found.model == "Genesis 23x11"
    assert found.filter_type is FilterType.SYNTHETIC
    assert found.usable_for(Method.STEAM_PREVAC, DAY)


def test_a_damaged_container_keeps_its_damage(containers: ContainerStore) -> None:
    containers.save(container(gasket_intact=False))
    assert not containers.get("RC-2001").gasket_intact


def test_a_retired_container_keeps_its_window(containers: ContainerStore) -> None:
    containers.save(container(in_service=DateRange(date(2019, 1, 1), date(2025, 1, 1))))
    assert not containers.get("RC-2001").in_service_on(DAY)


def test_an_unknown_container_is_refused(containers: ContainerStore) -> None:
    with pytest.raises(NotFoundError):
        containers.get("RC-9999")
    assert not containers.exists("RC-9999")


def test_a_cycle_moves_it_toward_its_inspection(containers: ContainerStore) -> None:
    containers.save(container(cycles_since_inspection=4))
    assert containers.used("RC-2001").cycles_since_inspection == 5
    assert containers.get("RC-2001").cycles_since_inspection == 5


def test_inspecting_resets_the_count(containers: ContainerStore) -> None:
    containers.save(container(cycles_since_inspection=80))
    found = containers.inspected("RC-2001", DAY)
    assert found.cycles_since_inspection == 0
    assert not containers.get("RC-2001").inspection_due(DAY)


def test_an_inspection_can_record_damage(containers: ContainerStore) -> None:
    containers.save(container())
    containers.inspected("RC-2001", DAY, latches_intact=False)
    assert not containers.get("RC-2001").latches_intact


def test_containers_due_for_inspection_are_listed(containers: ContainerStore) -> None:
    containers.save(container("RC-2001"))
    containers.save(container("RC-2002", last_inspection=None))
    assert [item.asset for item in containers.due_for_inspection(DAY)] == ["RC-2002"]


def test_containers_are_filtered_by_method(containers: ContainerStore) -> None:
    containers.save(container("RC-2001"))
    containers.save(container("RC-2002", filter_type=FilterType.PAPER))
    peroxide = containers.usable_for(Method.HYDROGEN_PEROXIDE, DAY)
    assert [item.asset for item in peroxide] == ["RC-2001"]
    steam = containers.usable_for(Method.STEAM_PREVAC, DAY)
    assert len(steam) == 2


def test_the_filter_burn_counts_only_working_containers(containers: ContainerStore) -> None:
    containers.save(container("RC-2001", filter_positions=2))
    containers.save(container("RC-2002", filter_type=FilterType.VALVE))
    containers.save(container("RC-2003", gasket_intact=False))
    assert containers.filters_needed(DAY) == 2


def test_a_container_that_cannot_run_anything_says_why(containers: ContainerStore) -> None:
    containers.save(container(gasket_intact=False))
    found = containers.get("RC-2001")
    assert found.refusal_on_any_method(DAY) == "the gasket does not seal"
    assert container().refusal_on_any_method(DAY) is None
