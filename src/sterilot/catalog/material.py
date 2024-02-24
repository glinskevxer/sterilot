"""What an instrument is made of, and what that rules out.

The manufacturer writes the instructions for use and the department follows
them, but the instructions come down to a handful of facts about the material:
how hot it can get, whether it survives peroxide, whether it can be immersed at
all. Holding those facts here means the count sheet can answer "can this set go
in the peroxide chamber" without anybody reading a binder.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sterilot.errors import ValidationError
from sterilot.ids import normalise_code
from sterilot.methods import Method
from sterilot.units.temperature import Temperature


class MaterialClass(Enum):
    """The families the department buys in."""

    STAINLESS = "stainless"
    TITANIUM = "titanium"
    ANODISED_ALUMINIUM = "anodised_aluminium"
    COPPER_ALLOY = "copper_alloy"
    CHROME_PLATED = "chrome_plated"
    RIGID_POLYMER = "rigid_polymer"
    SILICONE = "silicone"
    GLASS = "glass"
    CELLULOSE = "cellulose"
    ELECTRONIC = "electronic"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @classmethod
    def named(cls, value: str) -> MaterialClass:
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such material class", value=value)


@dataclass(frozen=True)
class Material:
    """One material, with the three facts that decide a method."""

    code: str
    name: str
    material_class: MaterialClass
    max_temperature: Temperature | None = None
    peroxide_safe: bool = True
    immersible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "code", normalise_code(self.code, field="material code", max_length=16)
        )
        if not self.name.strip():
            raise ValidationError("material name is empty", code=self.code)

    @property
    def is_cellulose(self) -> bool:
        return self.material_class is MaterialClass.CELLULOSE

    def refusal_for(self, method: Method) -> str | None:
        """Why this material cannot go through ``method``, or None."""
        if self.is_cellulose and not method.tolerates_cellulose:
            return "cellulose absorbs peroxide and aborts the cycle"
        if not self.peroxide_safe and method is Method.HYDROGEN_PEROXIDE:
            return "the material is attacked by vaporised peroxide"
        if self.material_class is MaterialClass.ELECTRONIC and method.is_steam:
            return "powered devices do not go in a steam chamber"
        if self.max_temperature is not None:
            ceiling = self.max_temperature
            if method.nominal_temperature.celsius > ceiling.celsius:
                return f"the material is rated to {ceiling.format()}"
        return None

    def tolerates(self, method: Method) -> bool:
        return self.refusal_for(method) is None

    def methods(self) -> tuple[Method, ...]:
        """Every method this material survives, in declaration order."""
        return tuple(method for method in Method if self.tolerates(method))


_STANDARD: tuple[Material, ...] = (
    Material("SS", "surgical stainless steel", MaterialClass.STAINLESS),
    Material("TI", "titanium", MaterialClass.TITANIUM),
    Material(
        "AL-AN",
        "anodised aluminium",
        MaterialClass.ANODISED_ALUMINIUM,
        max_temperature=Temperature(135.0),
    ),
    Material("BR", "brass and copper alloy", MaterialClass.COPPER_ALLOY, peroxide_safe=False),
    Material("CR", "chrome plated carbon steel", MaterialClass.CHROME_PLATED),
    Material(
        "PC",
        "rigid polymer, high temperature",
        MaterialClass.RIGID_POLYMER,
        max_temperature=Temperature(134.0),
    ),
    Material(
        "PL",
        "rigid polymer, low temperature",
        MaterialClass.RIGID_POLYMER,
        max_temperature=Temperature(60.0),
    ),
    Material("SIL", "silicone", MaterialClass.SILICONE),
    Material("GL", "borosilicate glass", MaterialClass.GLASS),
    Material("CEL", "cellulose, paper and cotton", MaterialClass.CELLULOSE),
    Material(
        "EL",
        "powered electronic handpiece",
        MaterialClass.ELECTRONIC,
        max_temperature=Temperature(60.0),
        immersible=False,
    ),
)


def standard_materials() -> dict[str, Material]:
    """The department's material list, keyed by code."""
    return {material.code: material for material in _STANDARD}


def material_named(code: str) -> Material:
    materials = standard_materials()
    wanted = normalise_code(code, field="material code", max_length=16)
    if wanted not in materials:
        raise ValidationError("no such material", code=wanted)
    return materials[wanted]
