from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.sterilizer.steam import (
    LoadKind,
    SteamQuality,
    dryness_band,
    non_condensable_band,
    superheat_band,
)

AT = datetime(2025, 5, 22, 6, 30)


def supply(**changes: object) -> SteamQuality:
    values: dict[str, object] = {
        "equipment": "ac 1",
        "at": AT,
        "by": "t 4471",
        "non_condensable_percent": 1.2,
        "dryness": 0.97,
        "superheat_k": 4.0,
    }
    values.update(changes)
    return SteamQuality(**values)  # type: ignore[arg-type]


def test_load_kinds_carry_their_own_dryness_floor() -> None:
    assert LoadKind.named("textile") is LoadKind.TEXTILE
    assert LoadKind.METAL.dryness_floor == pytest.approx(0.90)
    assert LoadKind.TEXTILE.dryness_floor == pytest.approx(0.95)
    with pytest.raises(ValidationError):
        LoadKind.named("plastic")


def test_the_bands_are_the_published_limits() -> None:
    assert non_condensable_band().contains(3.5)
    assert not non_condensable_band().contains(3.6)
    assert superheat_band().contains(25.0)
    assert not superheat_band().contains(25.1)
    assert dryness_band(LoadKind.TEXTILE).contains(0.95)
    assert not dryness_band(LoadKind.TEXTILE).contains(0.94)


def test_identifiers_are_normalised() -> None:
    made = supply()
    assert made.equipment == "AC-1"
    assert made.by == "T-4471"
    assert made.day == date(2025, 5, 22)


def test_impossible_readings_are_refused() -> None:
    with pytest.raises(ValidationError):
        supply(non_condensable_percent=-1.0)
    with pytest.raises(ValidationError):
        supply(dryness=0.0)
    with pytest.raises(ValidationError):
        supply(dryness=1.2)
    with pytest.raises(ValidationError):
        supply(superheat_k=-1.0)


def test_a_good_supply_passes_everything() -> None:
    made = supply()
    assert made.acceptable()
    assert made.problems() == ()
    assert set(made.good_for()) == set(LoadKind)


def test_too_much_air_in_the_steam_is_named() -> None:
    problems = supply(non_condensable_percent=6.0).problems()
    assert len(problems) == 1
    assert "non condensable 6.0 percent is 2.5 percent over" in problems[0]


def test_wet_steam_fails_a_textile_load_and_passes_a_metal_one() -> None:
    made = supply(dryness=0.92)
    assert not made.acceptable(LoadKind.TEXTILE)
    assert made.acceptable(LoadKind.METAL)
    assert made.good_for() == (LoadKind.METAL,)


def test_very_wet_steam_fails_both() -> None:
    made = supply(dryness=0.80)
    assert made.good_for() == ()
    assert "dryness 0.80" in made.problems(LoadKind.METAL)[0]


def test_superheated_steam_is_named() -> None:
    problems = supply(superheat_k=30.0).problems()
    assert "superheat 30.0 K is 5.0 K over" in problems[0]


def test_every_reading_is_explained_whether_it_passed_or_not() -> None:
    readings = supply().readings()
    assert len(readings) == 3
    assert all(
        "inside" in item or "no more than" in item or "at least" in item for item in readings
    )


def test_the_readings_follow_the_load_kind() -> None:
    made = supply(dryness=0.92)
    assert "under" in made.readings(LoadKind.TEXTILE)[1]
    assert "inside" in made.readings(LoadKind.METAL)[1]


def test_describe_reads_like_the_engineer_s_note() -> None:
    assert str(supply()) == ("AC-1 2025-05-22: 1.2 percent gas, dryness 0.97, superheat 4 K")
