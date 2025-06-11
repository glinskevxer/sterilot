"""Reading the instrument catalog from a file.

A department that has been running on paper has a spreadsheet with two thousand
catalog numbers in it, and typing those in one at a time is how a system fails
before it starts. So the catalog loads from delimited text, with the same
alias and reject handling as everything else here.

A row that would change an existing entry is reported rather than applied
unless the caller asks for it, because an import that quietly rewrites the
catalog is how a lumen measurement disappears.
"""

from __future__ import annotations

from dataclasses import dataclass

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named
from sterilot.errors import ValidationError
from sterilot.ingest.source import Row, RowProblem, read_delimited
from sterilot.units.mass import Mass

REQUIRED = ("catalog", "description", "manufacturer")

ALIASES = {
    "catalog_number": "catalog",
    "cat_no": "catalog",
    "item": "catalog",
    "name": "description",
    "vendor": "manufacturer",
    "maker": "manufacturer",
    "material_code": "material",
    "lumen_diameter_mm": "lumen_mm",
    "lumen_length": "lumen_length_mm",
    "weight_g": "grams",
    "mass_g": "grams",
}


@dataclass(frozen=True)
class CatalogImport:
    """What came out of one catalog file."""

    instruments: tuple[Instrument, ...] = ()
    changes: tuple[Instrument, ...] = ()
    problems: tuple[RowProblem, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        return (
            f"{len(self.instruments)} new, {len(self.changes)} changed,"
            f" {len(self.problems)} rejected"
        )


def _instrument(row: Row) -> Instrument:
    lumen = row.get("lumen_mm")
    length = row.get("lumen_length_mm")
    grams = row.get("grams")
    complexity = row.get("complexity") or ("lumened" if lumen or length else "simple")
    return Instrument(
        catalog=row.require("catalog"),
        description=row.require("description"),
        manufacturer=row.require("manufacturer"),
        material=material_named(row.get("material") or "SS"),
        complexity=Complexity.named(complexity),
        criticality=Criticality.named(row.get("criticality") or "critical"),
        lumen_diameter_mm=float(lumen) if lumen else None,
        lumen_length_mm=float(length) if length else None,
        requires_disassembly=_flag(row.get("disassembly")),
        insulated=_flag(row.get("insulated")),
        weight=Mass.of_grams(float(grams)) if grams else None,
    )


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "y", "yes", "true"}


def load_catalog(text: str, known: dict[str, Instrument] | None = None) -> CatalogImport:
    """Read a catalog file, separating new entries from changes to old ones."""
    stocked = known or {}
    result = read_delimited(text, required=REQUIRED, aliases=ALIASES)
    problems = list(result.problems)
    fresh: list[Instrument] = []
    changed: list[Instrument] = []
    seen: set[str] = set()
    for row in result.rows:
        try:
            item = _instrument(row)
        except (ValidationError, ValueError) as exc:
            problems.append(RowProblem(row.number, "will not build an instrument", str(exc)))
            continue
        if item.catalog in seen:
            problems.append(
                RowProblem(row.number, "repeats a catalog number in the same file", item.catalog)
            )
            continue
        seen.add(item.catalog)
        existing = stocked.get(item.catalog)
        if existing is None:
            fresh.append(item)
        elif existing != item:
            changed.append(item)
    return CatalogImport(tuple(fresh), tuple(changed), tuple(problems))
