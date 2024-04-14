from __future__ import annotations

from datetime import date

import pytest

from sterilot.assets.container import (
    INSPECTION_INTERVAL_CYCLES,
    Container,
    FilterType,
)
from sterilot.errors import ValidationError
from sterilot.interval import DateRange
from sterilot.methods import Method

DAY = date(2024, 5, 1)


def container(**changes: object) -> Container:
    values: dict[str, object] = {
        "asset": "rc 2001",
        "model": "Genesis 23x11",
        "manufacturer": "Aesculap",
        "filter_type": FilterType.SYNTHETIC,
        "last_inspection": date(2024, 4, 1),
    }
    values.update(changes)
    return Container(**values)  # type: ignore[arg-type]


def test_filter_types() -> None:
    assert FilterType.named("disposable paper") is FilterType.PAPER
    assert FilterType.named("VALVE") is FilterType.VALVE
    assert FilterType.PAPER.is_cellulose
    assert not FilterType.SYNTHETIC.is_cellulose
    assert FilterType.SYNTHETIC.single_use
    assert not FilterType.VALVE.single_use
    with pytest.raises(ValidationError):
        FilterType.named("cloth")


def test_asset_is_normalised_and_details_required() -> None:
    assert container().asset == "RC-2001"
    with pytest.raises(ValidationError):
        container(model=" ")
    with pytest.raises(ValidationError):
        container(manufacturer="")


def test_a_container_has_at_least_one_vent() -> None:
    with pytest.raises(ValidationError):
        container(filter_positions=0)


def test_a_negative_cycle_count_is_refused() -> None:
    with pytest.raises(ValidationError):
        container(cycles_since_inspection=-1)


def test_filters_per_cycle_follows_the_vents() -> None:
    assert container(filter_positions=2).filters_per_cycle == 2
    assert container(filter_type=FilterType.VALVE).filters_per_cycle == 0


def test_a_container_with_no_window_is_always_in_service() -> None:
    assert container().in_service_on(date(2030, 1, 1))


def test_a_retired_container_is_refused() -> None:
    item = container(in_service=DateRange(date(2020, 1, 1), date(2024, 1, 1)))
    assert not item.in_service_on(DAY)
    assert item.refusal_for(Method.STEAM_PREVAC, DAY) == "the container is not in service"


def test_inspection_falls_due_on_cycles() -> None:
    item = container(cycles_since_inspection=INSPECTION_INTERVAL_CYCLES)
    assert item.inspection_due(DAY)
    assert container(cycles_since_inspection=10).inspection_due(DAY) is False


def test_inspection_falls_due_on_the_calendar() -> None:
    item = container(last_inspection=date(2023, 4, 1))
    assert item.inspection_due(DAY)


def test_a_container_never_inspected_is_due() -> None:
    assert container(last_inspection=None).inspection_due(DAY)


def test_a_damaged_gasket_stops_everything() -> None:
    item = container(gasket_intact=False)
    assert item.refusal_for(Method.STEAM_PREVAC, DAY) == "the gasket does not seal"
    assert item.methods(DAY) == ()


def test_a_damaged_latch_stops_everything() -> None:
    assert container(latches_intact=False).refusal_for(Method.STEAM_GRAVITY, DAY) == (
        "a latch is damaged"
    )


def test_paper_filters_keep_a_container_out_of_the_peroxide_chamber() -> None:
    item = container(filter_type=FilterType.PAPER)
    assert not item.usable_for(Method.HYDROGEN_PEROXIDE, DAY)
    assert item.usable_for(Method.STEAM_PREVAC, DAY)
    assert Method.HYDROGEN_PEROXIDE not in item.methods(DAY)


def test_synthetic_filters_go_anywhere() -> None:
    assert set(container().methods(DAY)) == set(Method)


def test_a_cycle_moves_the_container_toward_its_inspection() -> None:
    item = container(cycles_since_inspection=4).after_cycle()
    assert item.cycles_since_inspection == 5
    assert item.asset == "RC-2001"


def test_inspecting_resets_the_count_and_the_date() -> None:
    item = container(cycles_since_inspection=80, last_inspection=date(2022, 1, 1))
    inspected = item.inspected(DAY)
    assert inspected.cycles_since_inspection == 0
    assert inspected.last_inspection == DAY
    assert not inspected.inspection_due(DAY)


def test_an_inspection_can_record_damage() -> None:
    inspected = container().inspected(DAY, gasket_intact=False)
    assert not inspected.gasket_intact
    assert inspected.refusal_for(Method.STEAM_PREVAC, DAY) == "the gasket does not seal"


def test_the_inspection_refusal_comes_before_the_filter_rule() -> None:
    item = container(filter_type=FilterType.PAPER, last_inspection=None)
    assert item.refusal_for(Method.HYDROGEN_PEROXIDE, DAY) == (
        "the container is due for inspection"
    )


def test_label() -> None:
    assert str(container()) == "RC-2001 Genesis 23x11"
