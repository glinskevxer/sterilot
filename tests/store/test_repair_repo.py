from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest

from sterilot.repair.order import RepairOrder, Status
from sterilot.store.repair_repo import RepairStore
from sterilot.store.store import Store

RAISED = datetime(2025, 9, 17, 9, 0)


@pytest.fixture
def repairs() -> Iterator[RepairStore]:
    store = Store.in_memory()
    yield store.repairs
    store.close()


def order(reference: str = "RP-1", asset: str = "INST-0912") -> RepairOrder:
    return RepairOrder(
        reference=reference,
        asset=asset,
        catalog="SU-2000",
        tray_code_out_of="ORT-MAJOR",
        vendor="Sharpline",
        fault="blade will not close",
        raised_at=RAISED,
        raised_by="T-4471",
    )


def test_orders_are_found_by_the_instrument_they_are_for(repairs: RepairStore) -> None:
    repairs.add(order("RP-1", "INST-0912"))
    repairs.add(order("RP-2", "INST-0913"))
    assert [item.reference for item in repairs.for_asset("inst 0912")] == ["RP-1"]
    assert repairs.for_asset("INST-9999") == ()


def test_an_instrument_with_two_orders_shows_both(repairs: RepairStore) -> None:
    repairs.add(order("RP-1"))
    repairs.save(order("RP-1").moved_to(Status.SENT, RAISED))
    repairs.add(order("RP-2"))
    assert len(repairs.for_asset("INST-0912")) == 2
