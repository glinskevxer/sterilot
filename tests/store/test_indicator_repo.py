from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.indicators.biological import BiologicalIndicator, Organism, Readout
from sterilot.indicators.chemical import ChemicalIndicator, IndicatorClass
from sterilot.methods import Method
from sterilot.store.indicator_repo import BIOLOGICAL, CHEMICAL, IndicatorStore
from sterilot.store.store import Store

DAY = date(2025, 5, 14)


@pytest.fixture
def indicators() -> Iterator[IndicatorStore]:
    store = Store.in_memory()
    yield store.indicators
    store.close()


def chemical(lot: str = "CI-25E01", **changes: object) -> ChemicalIndicator:
    values: dict[str, object] = {
        "indicator_class": IndicatorClass.INTEGRATING,
        "lot": lot,
        "expires_on": date(2026, 1, 31),
        "methods": frozenset({Method.STEAM_PREVAC, Method.STEAM_GRAVITY}),
    }
    values.update(changes)
    return ChemicalIndicator(**values)  # type: ignore[arg-type]


def biological(lot: str = "BI-25E02") -> BiologicalIndicator:
    return BiologicalIndicator(lot, Organism.STEAROTHERMOPHILUS, Readout.RAPID, date(2026, 3, 31))


def test_a_chemical_lot_round_trips(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical(), received_on=date(2025, 5, 1))
    found = indicators.chemical("ci 25e01")
    assert found.indicator_class is IndicatorClass.INTEGRATING
    assert found.suits(Method.STEAM_PREVAC)
    assert not found.suits(Method.HYDROGEN_PEROXIDE)


def test_an_emulating_lot_keeps_its_cycle(indicators: IndicatorStore) -> None:
    indicators.save_chemical(
        chemical(
            indicator_class=IndicatorClass.EMULATING,
            cycle_name="PREVAC-132",
            methods=frozenset({Method.STEAM_PREVAC}),
        )
    )
    found = indicators.chemical("CI-25E01")
    assert found.cycle_name == "PREVAC-132"
    assert found.suits(Method.STEAM_PREVAC, "prevac 132")


def test_a_biological_lot_round_trips(indicators: IndicatorStore) -> None:
    indicators.save_biological(biological())
    found = indicators.biological("BI-25E02")
    assert found.organism is Organism.STEAROTHERMOPHILUS
    assert found.readout is Readout.RAPID
    assert found.population_log == pytest.approx(6.0)


def test_the_two_families_are_kept_apart(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical())
    with pytest.raises(ValidationError):
        indicators.biological("CI-25E01")
    assert indicators.family_of("CI-25E01") == CHEMICAL


def test_a_lot_cannot_change_family(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical("CI-25E01"))
    with pytest.raises(ConflictError):
        indicators.save_biological(biological("CI-25E01"))


def test_an_unknown_lot_is_refused(indicators: IndicatorStore) -> None:
    with pytest.raises(NotFoundError):
        indicators.chemical("CI-9999")
    with pytest.raises(NotFoundError):
        indicators.family_of("CI-9999")
    with pytest.raises(NotFoundError):
        indicators.in_date("CI-9999", DAY)


def test_expiry_is_answered_from_the_register(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical())
    assert indicators.in_date("CI-25E01", DAY)
    assert not indicators.in_date("CI-25E01", date(2026, 6, 1))


def test_lots_about_to_run_out_are_listed(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical("CI-25E01", expires_on=date(2025, 6, 1)))
    indicators.save_chemical(chemical("CI-25E02", expires_on=date(2027, 1, 1)))
    found = indicators.expiring(DAY, 30)
    assert [lot for lot, _ in found] == ["CI-25E01"]
    assert indicators.expiring(DAY, 5) == ()


def test_a_retired_lot_drops_off_the_expiry_list(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical("CI-25E01", expires_on=date(2025, 6, 1)))
    indicators.retire("ci 25e01")
    assert indicators.expiring(DAY, 30) == ()


def test_a_negative_horizon_is_refused(indicators: IndicatorStore) -> None:
    with pytest.raises(ValidationError):
        indicators.expiring(DAY, -1)


def test_lots_are_listed_by_family(indicators: IndicatorStore) -> None:
    indicators.save_chemical(chemical())
    indicators.save_biological(biological())
    assert indicators.lots() == ("BI-25E02", "CI-25E01")
    assert indicators.lots(BIOLOGICAL) == ("BI-25E02",)
    assert indicators.lots(CHEMICAL) == ("CI-25E01",)
