from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord
from sterilot.load.release import ReleaseDecision, ReleaseKind
from sterilot.methods import Method
from sterilot.quality.metrics import (
    Turnaround,
    first_pass_yield,
    held_loads,
    rework_rate,
    summarise,
    throughput,
    turnaround_hours,
)
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


def record(
    reference: str,
    day: date,
    run: int,
    items: int = 1,
    kind: ReleaseKind | None = ReleaseKind.ROUTINE,
) -> LoadRecord:
    at = datetime.combine(day, datetime.min.time()).replace(hour=8)
    cycle = SterilizerCycle(
        LotControlNumber("AC-1", day, run),
        CycleSpec.standard(Method.STEAM_PREVAC),
        at,
        "T-4471",
        CycleMeasurements(Temperature(133.0), Duration.of_minutes(4), Duration.of_minutes(31)),
    )
    load = Load(
        reference,
        Method.STEAM_PREVAC,
        tuple(LoadItem(f"T-{reference}-{index}", "ORT-MAJOR", units=2) for index in range(items)),
        "T-4471",
        at,
    )
    made = LoadRecord(load, cycle)
    if kind is not None:
        made = made.decided(ReleaseDecision(kind, (), at, "T-4471"))
    return made


def test_summarise_describes_the_tail_as_well_as_the_middle() -> None:
    found = summarise([1.0, 2.0, 3.0, 4.0, 100.0])
    assert found.count == 5
    assert found.mean == pytest.approx(22.0)
    assert found.median == pytest.approx(3.0)
    assert found.highest == pytest.approx(100.0)
    assert found.lowest == pytest.approx(1.0)


def test_the_ninetieth_percentile_interpolates() -> None:
    found = summarise([10.0, 20.0])
    assert found.p90 == pytest.approx(19.0)


def test_a_single_value_summarises_to_itself() -> None:
    found = summarise([7.0])
    assert found.mean == found.median == found.p90 == pytest.approx(7.0)


def test_summarising_nothing_is_refused() -> None:
    with pytest.raises(ValidationError):
        summarise([])


def test_summary_describes_itself() -> None:
    assert summarise([1.0, 3.0]).describe(places=1) == ("n=2 mean=2.0 median=2.0 p90=2.8 worst=3.0")


def test_a_turnaround_cannot_finish_before_it_starts() -> None:
    with pytest.raises(ValidationError):
        Turnaround("ORT-0114", datetime(2024, 10, 2, 12, 0), datetime(2024, 10, 2, 9, 0))


def test_turnaround_hours_summarise_the_trays() -> None:
    runs = [
        Turnaround("ort 0114", datetime(2024, 10, 2, 8, 0), datetime(2024, 10, 2, 14, 0)),
        Turnaround("ORT-0115", datetime(2024, 10, 2, 8, 0), datetime(2024, 10, 3, 8, 0)),
    ]
    found = turnaround_hours(runs)
    assert found.count == 2
    assert found.lowest == pytest.approx(6.0)
    assert found.highest == pytest.approx(24.0)
    assert runs[0].asset == "ORT-0114"


def test_throughput_groups_by_day_oldest_first() -> None:
    records = [
        record("LD-1", date(2024, 10, 3), 1, items=2),
        record("LD-2", date(2024, 10, 2), 1, items=1),
        record("LD-3", date(2024, 10, 2), 2, items=3),
    ]
    totals = throughput(records)
    assert [item.day for item in totals] == [date(2024, 10, 2), date(2024, 10, 3)]
    assert totals[0].loads == 2
    assert totals[0].trays == 4
    assert totals[0].units == 8
    assert totals[0].trays_per_load == pytest.approx(2.0)


def test_a_day_with_no_loads_reports_no_ratio() -> None:
    totals = throughput([record("LD-1", date(2024, 10, 2), 1)])
    assert totals[0].trays_per_load == pytest.approx(1.0)


def test_first_pass_yield_counts_only_routine_releases() -> None:
    records = [
        record("LD-1", date(2024, 10, 2), 1),
        record("LD-2", date(2024, 10, 2), 2, kind=ReleaseKind.EMERGENCY),
        record("LD-3", date(2024, 10, 2), 3, kind=ReleaseKind.REJECTED),
        record("LD-4", date(2024, 10, 2), 4, kind=None),
    ]
    assert first_pass_yield(records) == pytest.approx(0.25)


def test_rework_counts_rejected_and_recalled() -> None:
    good = record("LD-1", date(2024, 10, 2), 1)
    bad = record("LD-2", date(2024, 10, 2), 2, kind=ReleaseKind.REJECTED)
    pulled = record("LD-3", date(2024, 10, 2), 3).recalled(
        datetime(2024, 10, 5, 9, 0), "positive biological"
    )
    assert rework_rate([good, bad, pulled]) == pytest.approx(2 / 3)


def test_measuring_nothing_is_refused() -> None:
    with pytest.raises(ValidationError):
        first_pass_yield([])
    with pytest.raises(ValidationError):
        rework_rate([])


def test_held_loads_are_listed() -> None:
    records = [
        record("LD-1", date(2024, 10, 2), 1),
        record("LD-2", date(2024, 10, 2), 2, kind=ReleaseKind.HELD),
    ]
    assert [item.reference for item in held_loads(records)] == ["LD-2"]
