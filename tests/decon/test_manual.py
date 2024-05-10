from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.catalog.instrument import Complexity, Instrument
from sterilot.catalog.material import material_named
from sterilot.decon.manual import (
    BrushSpec,
    ManualClean,
    PointOfUse,
    brush_for,
)
from sterilot.errors import ValidationError
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

CASE_END = datetime(2024, 5, 1, 11, 0)


def suction() -> Instrument:
    return Instrument(
        "SU-9001",
        "frazier suction tip",
        "Pilling",
        material_named("SS"),
        complexity=Complexity.LUMENED,
        lumen_diameter_mm=3.0,
        lumen_length_mm=160.0,
    )


def clamp() -> Instrument:
    return Instrument(
        "SU-1234", "kelly forceps", "V Mueller", material_named("SS"), complexity=Complexity.HINGED
    )


def trip(**changes: object) -> PointOfUse:
    values: dict[str, object] = {
        "case": "OR3-20240501-02",
        "finished_at": CASE_END,
        "collected_at": datetime(2024, 5, 1, 11, 40),
    }
    values.update(changes)
    return PointOfUse(**values)  # type: ignore[arg-type]


def clean(**changes: object) -> ManualClean:
    values: dict[str, object] = {
        "catalog": "SU-9001",
        "at": datetime(2024, 5, 1, 12, 15),
        "by": "T-4471",
        "soaked": Duration.of_minutes(4),
        "detergent_temperature": Temperature(35.0),
        "brush_mm": 4.0,
        "brush_passes": 3,
    }
    values.update(changes)
    return ManualClean(**values)  # type: ignore[arg-type]


def test_a_set_cannot_be_collected_before_the_case_ends() -> None:
    with pytest.raises(ValidationError):
        trip(collected_at=datetime(2024, 5, 1, 10, 0))


def test_a_prompt_clean_trip_has_no_problems() -> None:
    assert trip().problems() == ()
    assert trip().soak_factor() == pytest.approx(1.0)
    assert trip().delay.minutes == pytest.approx(40.0)


def test_a_long_delay_is_named_and_doubles_the_soak() -> None:
    late = trip(collected_at=datetime(2024, 5, 1, 15, 0))
    assert late.delayed
    assert late.problems() == ("the set sat 4h before collection",)
    assert late.soak_factor() == pytest.approx(2.0)


def test_a_dry_set_doubles_the_soak_even_when_collected_promptly() -> None:
    dry = trip(kept_moist=False)
    assert dry.soak_factor() == pytest.approx(2.0)
    assert "not kept moist" in dry.problems()[0]


def test_the_room_problems_are_all_reported() -> None:
    bad = trip(kept_moist=False, container_closed=False, gross_soil_removed=False)
    assert len(bad.problems()) == 3
    assert bad.problems()[0] == "gross soil was not removed in the room"


def test_a_brush_has_to_fit_the_channel() -> None:
    spec = BrushSpec(3.0)
    assert spec.fits(3.0)
    assert spec.fits(5.0)
    assert not spec.fits(2.9)
    assert not spec.fits(5.1)


def test_brush_for_only_answers_for_lumened_items() -> None:
    spec = brush_for(suction())
    assert spec is not None
    assert spec.diameter_mm == pytest.approx(3.0)
    assert brush_for(clamp()) is None


def test_a_clean_record_normalises_its_identifiers() -> None:
    record = ManualClean(
        "su 9001",
        datetime(2024, 5, 1, 12, 0),
        "t 4471",
        Duration.of_minutes(4),
        Temperature(35.0),
    )
    assert record.catalog == "SU-9001"
    assert record.by == "T-4471"


def test_negative_passes_and_a_zero_brush_are_refused() -> None:
    with pytest.raises(ValidationError):
        clean(brush_passes=-1)
    with pytest.raises(ValidationError):
        clean(brush_mm=0.0)


def test_a_record_judged_against_the_wrong_item_is_refused() -> None:
    with pytest.raises(ValidationError):
        clean().problems(clamp())


def test_a_good_clean_has_no_problems() -> None:
    assert clean().acceptable(suction())


def test_a_short_soak_names_the_gap() -> None:
    problems = clean(soaked=Duration.of_minutes(1)).problems(suction())
    assert problems[0] == "soak was 3m short of 4m"


def test_a_delayed_trip_lengthens_the_soak_requirement() -> None:
    late = trip(collected_at=datetime(2024, 5, 1, 16, 0))
    problems = clean().problems(suction(), late)
    assert problems[0] == "soak was 4m short of 8m"


def test_cold_detergent_is_named() -> None:
    problems = clean(detergent_temperature=Temperature(18.0)).problems(suction())
    assert any("detergent 18.0 C is 7.0 C under" in item for item in problems)


def test_a_missing_brush_on_a_lumen_is_named() -> None:
    problems = clean(brush_mm=None).problems(suction())
    assert "no brush was recorded for a lumened item" in problems


def test_a_brush_that_does_not_suit_the_channel_is_named() -> None:
    problems = clean(brush_mm=8.0).problems(suction())
    assert problems[0] == "brush 8.0 mm does not suit a 3.0 mm channel"


def test_too_few_passes_are_counted() -> None:
    problems = clean(brush_passes=1).problems(suction())
    assert "the lumen was brushed 1 times, not 3" in problems


def test_a_brush_on_a_solid_instrument_is_a_problem() -> None:
    record = clean(catalog="SU-1234", soaked=Duration.of_minutes(2))
    assert "a brush was recorded on an item with no channel" in record.problems(clamp())


def test_an_item_that_comes_apart_has_to_be_taken_apart() -> None:
    trocar = Instrument(
        "TR-1",
        "trocar assembly",
        "Applied",
        material_named("SS"),
        complexity=Complexity.MULTIPART,
        requires_disassembly=True,
    )
    record = ManualClean(
        "TR-1",
        datetime(2024, 5, 1, 12, 0),
        "T-4471",
        Duration.of_minutes(4),
        Temperature(35.0),
    )
    assert "the item was cleaned assembled" in record.problems(trocar)
    apart = ManualClean(
        "TR-1",
        datetime(2024, 5, 1, 12, 0),
        "T-4471",
        Duration.of_minutes(4),
        Temperature(35.0),
        disassembled=True,
    )
    assert apart.acceptable(trocar)
