from __future__ import annotations

import pytest

from tests.cli.conftest import invoke


@pytest.fixture
def dirty(db: str) -> str:
    invoke(
        db,
        "catalog",
        "add",
        "SU-9001",
        "frazier suction",
        "--manufacturer",
        "Pilling",
        "--complexity",
        "lumened",
        "--lumen-mm",
        "3.0",
        "--lumen-length-mm",
        "160",
    )
    invoke(
        db,
        "catalog",
        "add",
        "SU-1234",
        "kelly forceps",
        "--manufacturer",
        "V Mueller",
        "--complexity",
        "hinged",
    )
    return db


def record_trip(db: str, *extra: str) -> object:
    return invoke(
        db,
        "decon",
        "point-of-use",
        "OR3-01",
        "--finished",
        "2025-07-14 11:00",
        "--collected",
        "2025-07-14 11:40",
        *extra,
    )


def test_a_prompt_trip_is_recorded(dirty: str) -> None:
    result = record_trip(dirty)
    assert result.exit_code == 0  # type: ignore[attr-defined]
    assert "OR3-01 collected after 40m" in result.output  # type: ignore[attr-defined]


def test_a_dry_trip_doubles_the_soak(dirty: str) -> None:
    result = record_trip(dirty, "--dry")
    assert "not kept moist" in result.output  # type: ignore[attr-defined]
    assert "2 times the usual" in result.output  # type: ignore[attr-defined]


def test_every_room_problem_is_named(dirty: str) -> None:
    result = record_trip(dirty, "--dry", "--open-container", "--soil-left")
    assert "gross soil was not removed" in result.output  # type: ignore[attr-defined]
    assert "open container" in result.output  # type: ignore[attr-defined]


def test_a_good_sink_record_passes(dirty: str) -> None:
    result = invoke(
        dirty,
        "decon",
        "sink",
        "SU-9001",
        "--soak",
        "4",
        "--detergent-c",
        "35",
        "--brush-mm",
        "4.0",
        "--passes",
        "3",
    )
    assert result.exit_code == 0
    assert "SU-9001 cleaned" in result.output


def test_a_missing_brush_on_a_lumen_is_named(dirty: str) -> None:
    result = invoke(dirty, "decon", "sink", "SU-9001", "--soak", "4", "--detergent-c", "35")
    assert result.exit_code == 5
    assert "no brush was recorded" in result.output


def test_cold_detergent_is_named(dirty: str) -> None:
    result = invoke(dirty, "decon", "sink", "SU-1234", "--soak", "4", "--detergent-c", "15")
    assert result.exit_code == 5
    assert "detergent 15.0 C" in result.output


def test_a_delayed_trip_lengthens_the_soak_the_sink_needs(dirty: str) -> None:
    invoke(
        dirty,
        "decon",
        "point-of-use",
        "OR3-01",
        "--finished",
        "2025-07-14 11:00",
        "--collected",
        "2025-07-14 16:00",
    )
    result = invoke(
        dirty,
        "decon",
        "sink",
        "SU-1234",
        "--soak",
        "1",
        "--detergent-c",
        "35",
        "--case",
        "OR3-01",
    )
    assert result.exit_code == 5
    assert "short of 2m" in result.output


def test_a_case_with_no_trip_is_judged_on_its_own(dirty: str) -> None:
    result = invoke(
        dirty,
        "decon",
        "sink",
        "SU-1234",
        "--soak",
        "2",
        "--detergent-c",
        "35",
        "--case",
        "OR9-99",
    )
    assert result.exit_code == 0


def test_an_unstocked_item_exits_not_found(dirty: str) -> None:
    result = invoke(dirty, "decon", "sink", "SU-0000", "--soak", "4", "--detergent-c", "35")
    assert result.exit_code == 3


def test_the_day_lists_the_trips(dirty: str) -> None:
    record_trip(dirty)
    record_trip(dirty, "--dry")
    result = invoke(dirty, "decon", "day", "--on", "2025-07-14")
    assert "OR3-01" in result.output
    assert "not kept moist" in result.output


def test_the_sink_history_lists_every_clean(dirty: str) -> None:
    invoke(dirty, "decon", "sink", "SU-1234", "--soak", "2", "--detergent-c", "35")
    result = invoke(dirty, "decon", "sink-history", "SU-1234")
    assert "T-4471" in result.output
    assert "2m" in result.output
