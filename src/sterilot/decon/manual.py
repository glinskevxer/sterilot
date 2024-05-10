"""Point of use treatment and manual cleaning at the sink.

The washer gets the credit and the sink does the work. A lumen that was not
brushed is not clean when it comes out of the machine, and dried blood that sat
in a box lock for six hours will still be there afterwards.

Two things are recorded because two things go wrong. What happened to the set
between the case and the dock, and what happened to it at the sink.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sterilot.catalog.instrument import Instrument
from sterilot.errors import ValidationError
from sterilot.ids import badge_number, case_number, catalog_number
from sterilot.tolerance import Band
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature

TRANSPORT_LIMIT = Duration.of_hours(2)
"""How long a soiled set may sit before the soak requirement grows."""

DELAYED_SOAK_FACTOR = 2.0
BRUSH_CLEARANCE_MM = 2.0
MINIMUM_BRUSH_PASSES = 3
DETERGENT_BAND = Band.between(25.0, 45.0, label="detergent")


@dataclass(frozen=True)
class PointOfUse:
    """What the room did with the set before it left."""

    case: str
    finished_at: datetime
    collected_at: datetime
    kept_moist: bool = True
    container_closed: bool = True
    gross_soil_removed: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "case", case_number(self.case))
        if self.collected_at < self.finished_at:
            raise ValidationError(
                "the set cannot be collected before the case ends", case=self.case
            )

    @property
    def delay(self) -> Duration:
        return Duration((self.collected_at - self.finished_at).total_seconds())

    @property
    def delayed(self) -> bool:
        return self.delay.seconds > TRANSPORT_LIMIT.seconds

    def problems(self) -> tuple[str, ...]:
        found: list[str] = []
        if not self.gross_soil_removed:
            found.append("gross soil was not removed in the room")
        if not self.kept_moist:
            found.append("the set was not kept moist")
        if not self.container_closed:
            found.append("the set travelled in an open container")
        if self.delayed:
            found.append(f"the set sat {self.delay.spelled()} before collection")
        return tuple(found)

    def soak_factor(self) -> float:
        """How much longer the sink soak has to be because of this trip."""
        if self.delayed or not self.kept_moist:
            return DELAYED_SOAK_FACTOR
        return 1.0


@dataclass(frozen=True)
class BrushSpec:
    """The brush a lumen needs."""

    diameter_mm: float
    passes: int = MINIMUM_BRUSH_PASSES

    def fits(self, brush_mm: float) -> bool:
        return self.diameter_mm <= brush_mm <= self.diameter_mm + BRUSH_CLEARANCE_MM


def brush_for(item: Instrument) -> BrushSpec | None:
    """The brush spec for a lumened item, or None when it has no channel."""
    if not item.has_lumen or item.lumen_diameter_mm is None:
        return None
    return BrushSpec(item.lumen_diameter_mm)


@dataclass(frozen=True)
class ManualClean:
    """One instrument, cleaned by hand, recorded."""

    catalog: str
    at: datetime
    by: str
    soaked: Duration
    detergent_temperature: Temperature
    brush_mm: float | None = None
    brush_passes: int = 0
    disassembled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "catalog", catalog_number(self.catalog))
        object.__setattr__(self, "by", badge_number(self.by))
        if self.brush_passes < 0:
            raise ValidationError("brush passes cannot be negative", catalog=self.catalog)
        if self.brush_mm is not None and self.brush_mm <= 0:
            raise ValidationError("a brush has a diameter", catalog=self.catalog)

    def required_soak(self, item: Instrument, point_of_use: PointOfUse | None = None) -> Duration:
        factor = point_of_use.soak_factor() if point_of_use is not None else 1.0
        return Duration.of_minutes(item.sink_minutes * factor)

    def problems(self, item: Instrument, point_of_use: PointOfUse | None = None) -> tuple[str, ...]:
        """Everything wrong with this clean, given the item it was done on."""
        if item.catalog != self.catalog:
            raise ValidationError(
                "that record is for a different item", record=self.catalog, item=item.catalog
            )
        found: list[str] = []
        required = self.required_soak(item, point_of_use)
        if self.soaked.seconds < required.seconds:
            short = self.soaked.shortfall_against(required)
            found.append(f"soak was {short.spelled()} short of {required.spelled()}")
        reading = DETERGENT_BAND.evaluate(self.detergent_temperature.celsius)
        if not reading.passed:
            found.append(reading.explain(unit="C"))
        spec = brush_for(item)
        if spec is not None:
            if self.brush_mm is None:
                found.append("no brush was recorded for a lumened item")
            elif not spec.fits(self.brush_mm):
                found.append(
                    f"brush {self.brush_mm:.1f} mm does not suit a "
                    f"{spec.diameter_mm:.1f} mm channel"
                )
            if self.brush_passes < spec.passes:
                found.append(f"the lumen was brushed {self.brush_passes} times, not {spec.passes}")
        elif self.brush_mm is not None:
            found.append("a brush was recorded on an item with no channel")
        if item.requires_disassembly and not self.disassembled:
            found.append("the item was cleaned assembled")
        return tuple(found)

    def acceptable(self, item: Instrument, point_of_use: PointOfUse | None = None) -> bool:
        return not self.problems(item, point_of_use)
