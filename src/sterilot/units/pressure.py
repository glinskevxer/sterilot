"""Chamber pressure, and the saturated steam curve that goes with it.

Steam sterilization works because saturated steam condenses on the load and
gives up its latent heat. Steam that is hotter than its own pressure says it
should be is superheated, it behaves like hot air, and it does not sterilize on
the printed cycle time. So pressure is not a decorative field on a cycle
record: read together with temperature it says whether the cycle had steam in
it at all.

The saturation curve is Antoine, in the two ranges the coefficients are fitted
for. That is accurate to a fraction of a degree across everything a hospital
sterilizer does, which is well inside the resolution of the chamber probe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sterilot.errors import ValidationError
from sterilot.units.temperature import Temperature

ATMOSPHERE_KPA = 101.325
MMHG_PER_KPA = 7.50062
PSI_PER_KPA = 0.145038

_LOW_RANGE = (8.07131, 1730.63, 233.426)
_HIGH_RANGE = (8.14019, 1810.94, 244.485)
_RANGE_SPLIT_C = 99.0


@dataclass(frozen=True, order=True)
class Pressure:
    """An absolute pressure in kilopascals."""

    kilopascals: float

    def __post_init__(self) -> None:
        if self.kilopascals < 0:
            raise ValidationError(
                "absolute pressure cannot be negative", kilopascals=self.kilopascals
            )
        if self.kilopascals > 2000.0:
            raise ValidationError(
                "pressure is far above anything a sterilizer chamber sees",
                kilopascals=self.kilopascals,
            )

    @classmethod
    def from_kpa_absolute(cls, value: float) -> Pressure:
        return cls(float(value))

    @classmethod
    def from_kpa_gauge(cls, value: float) -> Pressure:
        return cls(float(value) + ATMOSPHERE_KPA)

    @classmethod
    def from_psia(cls, value: float) -> Pressure:
        return cls(float(value) / PSI_PER_KPA)

    @classmethod
    def from_psig(cls, value: float) -> Pressure:
        return cls(float(value) / PSI_PER_KPA + ATMOSPHERE_KPA)

    @classmethod
    def from_bar_absolute(cls, value: float) -> Pressure:
        return cls(float(value) * 100.0)

    @classmethod
    def from_mmhg(cls, value: float) -> Pressure:
        return cls(float(value) / MMHG_PER_KPA)

    @classmethod
    def atmospheric(cls) -> Pressure:
        return cls(ATMOSPHERE_KPA)

    @property
    def gauge_kpa(self) -> float:
        return self.kilopascals - ATMOSPHERE_KPA

    @property
    def psia(self) -> float:
        return self.kilopascals * PSI_PER_KPA

    @property
    def psig(self) -> float:
        return self.gauge_kpa * PSI_PER_KPA

    @property
    def bar(self) -> float:
        return self.kilopascals / 100.0

    @property
    def mmhg(self) -> float:
        return self.kilopascals * MMHG_PER_KPA

    def is_vacuum(self) -> bool:
        """True when the chamber is below the room."""
        return self.kilopascals < ATMOSPHERE_KPA

    def format(self, unit: str = "kpa", places: int = 1) -> str:
        wanted = unit.lower()
        if wanted == "kpa":
            return f"{self.kilopascals:.{places}f} kPa"
        if wanted == "psia":
            return f"{self.psia:.{places}f} psia"
        if wanted == "psig":
            return f"{self.psig:.{places}f} psig"
        if wanted == "bar":
            return f"{self.bar:.{places}f} bar"
        if wanted == "mmhg":
            return f"{self.mmhg:.{places}f} mmHg"
        raise ValidationError("unknown pressure unit", unit=unit)

    def __str__(self) -> str:
        return self.format()


def saturation_pressure(temperature: Temperature) -> Pressure:
    """The pressure saturated steam sits at for a given temperature."""
    celsius = temperature.celsius
    if celsius <= 0.0:
        raise ValidationError("no steam curve below freezing", celsius=celsius)
    a, b, c = _LOW_RANGE if celsius < _RANGE_SPLIT_C else _HIGH_RANGE
    mmhg = 10.0 ** (a - b / (c + celsius))
    return Pressure.from_mmhg(mmhg)


def saturation_temperature(pressure: Pressure) -> Temperature:
    """The temperature saturated steam sits at for a given pressure."""
    if pressure.kilopascals <= 0.0:
        raise ValidationError("no steam curve at zero pressure")
    mmhg = pressure.mmhg
    for a, b, c in (_LOW_RANGE, _HIGH_RANGE):
        celsius = b / (a - math.log10(mmhg)) - c
        in_low = celsius < _RANGE_SPLIT_C
        if in_low == ((a, b, c) == _LOW_RANGE):
            return Temperature(celsius)
    return Temperature(_HIGH_RANGE[1] / (_HIGH_RANGE[0] - math.log10(mmhg)) - _HIGH_RANGE[2])


def superheat(temperature: Temperature, pressure: Pressure) -> float:
    """Degrees the chamber runs above its own saturation temperature.

    Zero or a small negative number is ordinary. A positive number of any size
    means the steam is not saturated and the cycle is not doing what the
    printed exposure time claims.
    """
    return temperature.difference(saturation_temperature(pressure))
