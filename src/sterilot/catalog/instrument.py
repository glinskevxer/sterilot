"""A catalog item: one kind of instrument, not one physical instrument.

The physical ones live in trays and get counted. This is the entry the count
sheet points at, and it carries the facts that decide how the instrument is
cleaned and which chamber it can go in.

Lumens are the reason this is not just a name and a material. A long narrow
channel is the hardest thing in the department to clean and the hardest thing
to sterilize, and both low temperature methods publish a lumen limit that a
material lookup knows nothing about.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sterilot.catalog.material import Material
from sterilot.errors import ValidationError
from sterilot.ids import catalog_number
from sterilot.methods import Method
from sterilot.units.mass import Mass

PEROXIDE_MIN_LUMEN_MM = 1.0
PEROXIDE_MAX_LUMEN_LENGTH_MM = 500.0


class Complexity(Enum):
    """How much work the instrument is at the sink and on the bench."""

    SIMPLE = "simple"
    HINGED = "hinged"
    LUMENED = "lumened"
    MULTIPART = "multipart"
    POWERED = "powered"

    @property
    def label(self) -> str:
        return self.value

    @property
    def manual_clean_minutes(self) -> float:
        return {
            "simple": 0.5,
            "hinged": 1.0,
            "lumened": 4.0,
            "multipart": 3.0,
            "powered": 5.0,
        }[self.value]

    @classmethod
    def named(cls, value: str) -> Complexity:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such complexity", value=value)


class Criticality(Enum):
    """Spaulding, which decides whether the item must be sterile at all."""

    CRITICAL = "critical"
    SEMICRITICAL = "semicritical"
    NONCRITICAL = "noncritical"

    @property
    def must_be_sterile(self) -> bool:
        return self is Criticality.CRITICAL

    @classmethod
    def named(cls, value: str) -> Criticality:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such criticality", value=value)


@dataclass(frozen=True)
class Instrument:
    """One catalog entry."""

    catalog: str
    description: str
    manufacturer: str
    material: Material
    complexity: Complexity = Complexity.SIMPLE
    criticality: Criticality = Criticality.CRITICAL
    lumen_diameter_mm: float | None = None
    lumen_length_mm: float | None = None
    requires_disassembly: bool = False
    insulated: bool = False
    weight: Mass | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "catalog", catalog_number(self.catalog))
        if not self.description.strip():
            raise ValidationError("catalog entry has no description", catalog=self.catalog)
        if not self.manufacturer.strip():
            raise ValidationError("catalog entry has no manufacturer", catalog=self.catalog)
        has_lumen = self.lumen_diameter_mm is not None or self.lumen_length_mm is not None
        if has_lumen and self.complexity is not Complexity.LUMENED:
            raise ValidationError(
                "an item with a lumen has to be marked lumened", catalog=self.catalog
            )
        if self.complexity is Complexity.LUMENED and not has_lumen:
            raise ValidationError("a lumened item needs its channel measured", catalog=self.catalog)
        for value, field in (
            (self.lumen_diameter_mm, "lumen_diameter_mm"),
            (self.lumen_length_mm, "lumen_length_mm"),
        ):
            if value is not None and value <= 0:
                raise ValidationError("a lumen measurement must be positive", field=field)
        if self.insulated and self.complexity is Complexity.SIMPLE:
            raise ValidationError(
                "insulated items are never simple to reprocess", catalog=self.catalog
            )

    @property
    def has_lumen(self) -> bool:
        return self.complexity is Complexity.LUMENED

    @property
    def sink_minutes(self) -> float:
        """Manual cleaning time, longer when the item comes apart."""
        base = self.complexity.manual_clean_minutes
        return base + 1.0 if self.requires_disassembly else base

    def refusal_for(self, method: Method) -> str | None:
        """Why this item cannot go through ``method``, or None."""
        material_reason = self.material.refusal_for(method)
        if material_reason is not None:
            return material_reason
        if method is Method.HYDROGEN_PEROXIDE and self.has_lumen:
            if (
                self.lumen_diameter_mm is not None
                and self.lumen_diameter_mm < PEROXIDE_MIN_LUMEN_MM
            ):
                return f"lumen is narrower than {PEROXIDE_MIN_LUMEN_MM:.0f} mm"
            if (
                self.lumen_length_mm is not None
                and self.lumen_length_mm > PEROXIDE_MAX_LUMEN_LENGTH_MM
            ):
                return f"lumen is longer than {PEROXIDE_MAX_LUMEN_LENGTH_MM:.0f} mm"
        return None

    def tolerates(self, method: Method) -> bool:
        return self.refusal_for(method) is None

    def methods(self) -> tuple[Method, ...]:
        return tuple(method for method in Method if self.tolerates(method))

    def label(self) -> str:
        return f"{self.catalog} {self.description}"

    def __str__(self) -> str:
        return self.label()
