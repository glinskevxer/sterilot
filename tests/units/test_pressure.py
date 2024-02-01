from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.units.pressure import (
    ATMOSPHERE_KPA,
    Pressure,
    saturation_pressure,
    saturation_temperature,
    superheat,
)
from sterilot.units.temperature import Temperature


def test_absolute_is_what_is_stored() -> None:
    assert Pressure(304.0).kilopascals == pytest.approx(304.0)


def test_negative_absolute_is_refused() -> None:
    with pytest.raises(ValidationError):
        Pressure(-1.0)


def test_absurd_pressure_is_refused() -> None:
    with pytest.raises(ValidationError):
        Pressure(5000.0)


def test_gauge_and_absolute_agree_at_the_room() -> None:
    room = Pressure.atmospheric()
    assert room.gauge_kpa == pytest.approx(0.0)
    assert Pressure.from_kpa_gauge(0.0) == room


def test_psi_round_trips() -> None:
    assert Pressure.from_psig(30.0).psig == pytest.approx(30.0)
    assert Pressure.from_psia(44.0).psia == pytest.approx(44.0)


def test_bar_and_mmhg_round_trip() -> None:
    assert Pressure.from_bar_absolute(3.04).bar == pytest.approx(3.04)
    assert Pressure.from_mmhg(760.0).mmhg == pytest.approx(760.0)


def test_one_atmosphere_is_about_fourteen_seven_psia() -> None:
    assert Pressure.atmospheric().psia == pytest.approx(14.696, abs=0.01)


def test_vacuum_is_anything_below_the_room() -> None:
    assert Pressure(8.0).is_vacuum()
    assert not Pressure(ATMOSPHERE_KPA).is_vacuum()
    assert not Pressure(304.0).is_vacuum()


def test_format_in_each_unit() -> None:
    reading = Pressure(304.0)
    assert reading.format() == "304.0 kPa"
    assert reading.format("psig") == "29.4 psig"
    assert reading.format("bar", places=2) == "3.04 bar"
    assert reading.format("PSIA") == "44.1 psia"
    assert reading.format("mmhg", places=0) == "2280 mmHg"
    assert str(reading) == "304.0 kPa"


def test_format_refuses_an_unknown_unit() -> None:
    with pytest.raises(ValidationError):
        Pressure(304.0).format("torr")


def test_ordering() -> None:
    assert Pressure(101.325) < Pressure(304.0)


@pytest.mark.parametrize(
    ("celsius", "kpa"),
    [
        (100.0, 101.3),
        (121.1, 204.9),
        (134.0, 302.3),
        (60.0, 19.9),
    ],
)
def test_saturation_pressure_matches_the_steam_tables(celsius: float, kpa: float) -> None:
    assert saturation_pressure(Temperature(celsius)).kilopascals == pytest.approx(kpa, rel=0.01)


def test_saturation_curve_inverts_itself() -> None:
    for celsius in (40.0, 80.0, 100.0, 121.1, 134.0):
        reading = Temperature(celsius)
        back = saturation_temperature(saturation_pressure(reading))
        assert back.celsius == pytest.approx(celsius, abs=0.05)


def test_saturation_pressure_refuses_freezing() -> None:
    with pytest.raises(ValidationError):
        saturation_pressure(Temperature(0.0))


def test_saturation_temperature_refuses_no_pressure() -> None:
    with pytest.raises(ValidationError):
        saturation_temperature(Pressure(0.0))


def test_a_saturated_chamber_reads_no_superheat() -> None:
    chamber = Temperature(134.0)
    reading = superheat(chamber, saturation_pressure(chamber))
    assert reading == pytest.approx(0.0, abs=0.05)


def test_superheat_is_positive_when_the_chamber_runs_hot_for_its_pressure() -> None:
    reading = superheat(Temperature(140.0), saturation_pressure(Temperature(134.0)))
    assert reading == pytest.approx(6.0, abs=0.1)


def test_wet_steam_reads_slightly_negative() -> None:
    reading = superheat(Temperature(133.0), saturation_pressure(Temperature(134.0)))
    assert reading < 0
