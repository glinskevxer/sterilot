from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.repair.attrition import AttritionTable, Loss, Period


def period(
    year: int = 2023,
    opening: int = 100,
    catalog: str = "su 1234",
    code: str = "ort major",
    **changes: object,
) -> Period:
    values: dict[str, object] = {
        "year": year,
        "code": code,
        "catalog": catalog,
        "opening": opening,
        "losses": {Loss.BROKEN: 3, Loss.MISSING: 5},
    }
    values.update(changes)
    return Period(**values)  # type: ignore[arg-type]


def test_loss_lookup_and_repairability() -> None:
    assert Loss.named("missing") is Loss.MISSING
    assert Loss.BROKEN.repairable
    assert not Loss.MISSING.repairable
    with pytest.raises(ValidationError):
        Loss.named("evaporated")


def test_identifiers_are_normalised() -> None:
    made = period()
    assert made.code == "ORT-MAJOR"
    assert made.catalog == "SU-1234"


def test_negative_counts_are_refused() -> None:
    with pytest.raises(ValidationError):
        period(opening=-1)
    with pytest.raises(ValidationError):
        period(purchased=-1)
    with pytest.raises(ValidationError):
        period(losses={Loss.BROKEN: -1})


def test_losing_more_than_ever_existed_is_refused() -> None:
    with pytest.raises(ValidationError):
        period(opening=2, losses={Loss.MISSING: 9})


def test_the_arithmetic_of_a_year() -> None:
    made = period(purchased=4)
    assert made.lost == 8
    assert made.closing == 96
    assert made.rate == pytest.approx(0.08)
    assert made.repairable == 3
    assert made.losses_of(Loss.MISSING) == 5
    assert made.losses_of(Loss.WORN) == 0


def test_a_set_that_started_empty_has_no_rate() -> None:
    assert period(opening=0, losses={}).rate == pytest.approx(0.0)


def test_describe_reads_like_the_annual_sheet() -> None:
    assert period().describe() == "2023 ORT-MAJOR SU-1234: 100 opening, 8 lost, 92 closing"


def test_the_table_groups_by_set_and_catalog() -> None:
    table = AttritionTable.of([period(2022), period(2023), period(2023, catalog="SU-1235")])
    assert len(table.for_item("ORT-MAJOR", "SU-1234")) == 2
    assert len(table.for_item("ORT-MAJOR", "SU-1235")) == 1
    assert table.for_item("GEN-MINOR", "SU-1234") == ()


def test_the_rate_is_weighted_by_what_was_in_service() -> None:
    table = AttritionTable.of(
        [period(2022, opening=100), period(2023, opening=300, losses={Loss.MISSING: 8})]
    )
    assert table.rate_for("ORT-MAJOR", "SU-1234") == pytest.approx(16 / 400)


def test_an_item_with_no_history_has_no_rate() -> None:
    assert AttritionTable().rate_for("ORT-MAJOR", "SU-1234") == pytest.approx(0.0)


def test_a_forecast_rounds_up_to_whole_instruments() -> None:
    table = AttritionTable.of([period(opening=100)])
    assert table.forecast("ORT-MAJOR", "SU-1234", on_hand=50) == 4
    assert table.forecast("ORT-MAJOR", "SU-1234", on_hand=50, years=2) == 8


def test_a_forecast_of_nothing_needed_is_zero() -> None:
    table = AttritionTable.of([period(losses={})])
    assert table.forecast("ORT-MAJOR", "SU-1234", on_hand=50) == 0


def test_a_forecast_refuses_nonsense() -> None:
    table = AttritionTable.of([period()])
    with pytest.raises(ValidationError):
        table.forecast("ORT-MAJOR", "SU-1234", on_hand=-1)
    with pytest.raises(ValidationError):
        table.forecast("ORT-MAJOR", "SU-1234", on_hand=10, years=0)


def test_worst_lists_the_biggest_losers_first() -> None:
    table = AttritionTable.of(
        [
            period(catalog="SU-1234", opening=100, losses={Loss.MISSING: 2}),
            period(catalog="SU-1235", opening=100, losses={Loss.MISSING: 20}),
            period(catalog="SU-1236", opening=100, losses={Loss.MISSING: 9}),
        ]
    )
    worst = table.worst(limit=2)
    assert [row[1] for row in worst] == ["SU-1235", "SU-1236"]
    assert worst[0][2] == pytest.approx(0.2)


def test_worst_needs_a_real_limit() -> None:
    with pytest.raises(ValidationError):
        AttritionTable.of([period()]).worst(limit=0)
