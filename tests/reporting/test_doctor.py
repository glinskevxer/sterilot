from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pytest

from sterilot.assets.container import Container, FilterType
from sterilot.indicators.chemical import ChemicalIndicator, IndicatorClass
from sterilot.methods import Method
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.reporting import doctor
from sterilot.reporting.doctor import Level
from sterilot.staff.tech import Role, Technician
from sterilot.sterilizer.equipment import Sterilizer
from sterilot.storage.shelf import Location, Zone
from sterilot.store.store import Store

DAY = date(2025, 6, 24)


@pytest.fixture
def store() -> Iterator[Store]:
    made = Store.in_memory()
    yield made
    made.close()


def chamber(**changes: object) -> Sterilizer:
    values: dict[str, object] = {
        "equipment": "AC-1",
        "model": "Amsco 400",
        "manufacturer": "Steris",
        "methods": frozenset({Method.STEAM_PREVAC}),
    }
    values.update(changes)
    return Sterilizer(**values)  # type: ignore[arg-type]


def test_a_quiet_department_is_clear(store: Store) -> None:
    report = doctor.check(store, DAY)
    assert report.clear
    assert "nothing outstanding" in report.render()


def test_a_chamber_owing_qualification_runs_stops_the_check(store: Store) -> None:
    store.equipment.save_sterilizer(chamber().repaired())
    report = doctor.check(store, DAY)
    assert not report.clear
    assert report.stops[0].area == "sterilizer"
    assert "owes 3 qualification runs" in report.stops[0].detail


def test_an_overdue_exception_is_a_stop_and_a_fresh_one_is_a_note(store: Store) -> None:
    store.quality.save_exception(
        Nonconformance(
            "NC-1",
            Category.STERILIZATION,
            Severity.MINOR,
            datetime(2025, 5, 1, 9, 0),
            "T-4471",
            "wet pack",
        )
    )
    store.quality.save_exception(
        Nonconformance(
            "NC-2",
            Category.ASSEMBLY,
            Severity.MINOR,
            datetime(2025, 6, 23, 9, 0),
            "T-4471",
            "tray short",
        )
    )
    report = doctor.check(store, DAY)
    levels = {item.subject: item.level for item in report.findings}
    assert levels["NC-1"] is Level.STOP
    assert levels["NC-2"] is Level.NOTE


def test_a_container_due_for_inspection_is_reported(store: Store) -> None:
    store.containers.save(
        Container("RC-2001", "Genesis", "Aesculap", FilterType.SYNTHETIC, last_inspection=None)
    )
    report = doctor.check(store, DAY)
    assert any(item.area == "container" for item in report.findings)


def test_an_expired_indicator_lot_is_a_stop(store: Store) -> None:
    store.indicators.save_chemical(
        ChemicalIndicator(
            IndicatorClass.INTEGRATING,
            "CI-25A01",
            date(2025, 6, 1),
            frozenset({Method.STEAM_PREVAC}),
        )
    )
    report = doctor.check(store, DAY)
    assert report.stops[0].area == "indicator"


def test_a_lot_expiring_soon_is_only_a_warning(store: Store) -> None:
    store.indicators.save_chemical(
        ChemicalIndicator(
            IndicatorClass.INTEGRATING,
            "CI-25A01",
            date(2025, 7, 20),
            frozenset({Method.STEAM_PREVAC}),
        )
    )
    report = doctor.check(store, DAY)
    assert report.stops == ()
    assert report.findings[0].level is Level.SOON


def test_a_bad_storage_location_is_a_stop(store: Store) -> None:
    store.packages.save_location(
        Location("ST-B1", "under the sink", Zone.STERILE_STORE, 6, 10.0, 20.0, under_plumbing=True)
    )
    report = doctor.check(store, DAY)
    assert any(item.area == "storage" for item in report.stops)


def test_a_technician_who_cannot_release_is_reported(store: Store) -> None:
    store.staff.save(Technician("T-4471", "R Ferreira", Role.TECHNICIAN))
    report = doctor.check(store, DAY)
    assert any(item.area == "staff" for item in report.findings)


def test_a_trainee_is_not_reported(store: Store) -> None:
    store.staff.save(Technician("T-9100", "A Novak", Role.TRAINEE))
    assert doctor.check(store, DAY).clear


def test_findings_sort_worst_first(store: Store) -> None:
    store.equipment.save_sterilizer(chamber().repaired())
    store.containers.save(
        Container("RC-2001", "Genesis", "Aesculap", FilterType.SYNTHETIC, last_inspection=None)
    )
    report = doctor.check(store, DAY)
    assert [item.level for item in report.findings] == sorted(
        (item.level for item in report.findings), key=lambda level: level.rank
    )


def test_a_finding_describes_itself(store: Store) -> None:
    store.equipment.save_sterilizer(chamber(out_of_order=True))
    finding = doctor.check(store, DAY).findings[0]
    assert finding.describe() == "[stop] sterilizer AC-1: the sterilizer is out of order"


def test_the_report_renders_as_a_table(store: Store) -> None:
    store.equipment.save_sterilizer(chamber(out_of_order=True))
    rendered = doctor.check(store, DAY).render()
    assert "Department check 2025-06-24" in rendered
    assert "AC-1" in rendered
    assert "level" in rendered
