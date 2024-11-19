"""Reading and writing the catalog.

Instruments and count sheets, with sheet revisions stored as rows rather than
as a rewrite. Asking for a sheet is always asking for a day, because that is
the only question the assembly bench ever has.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.revision import Revision, RevisionHistory
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import NotFoundError
from sterilot.ids import catalog_number, tray_code
from sterilot.interval import DateRange
from sterilot.store import rows
from sterilot.store.db import Database

_INSTRUMENT_COLUMNS = (
    "catalog, description, manufacturer, material, complexity, criticality,"
    " lumen_mm, lumen_len_mm, disassembly, insulated, weight_g"
)


@dataclass
class CatalogStore:
    """Instruments and sheets in one place, because they are read together."""

    db: Database

    def save_instrument(self, item: Instrument) -> None:
        self.db.execute(
            f"INSERT OR REPLACE INTO instrument ({_INSTRUMENT_COLUMNS})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                item.catalog,
                item.description,
                item.manufacturer,
                item.material.code,
                item.complexity.value,
                item.criticality.value,
                item.lumen_diameter_mm,
                item.lumen_length_mm,
                rows.put_bool(item.requires_disassembly),
                rows.put_bool(item.insulated),
                rows.put_grams(item.weight),
            ],
        )

    def instrument(self, catalog: str) -> Instrument:
        wanted = catalog_number(catalog)
        row = self.db.query_one(
            f"SELECT {_INSTRUMENT_COLUMNS} FROM instrument WHERE catalog = ?", [wanted]
        )
        if row is None:
            raise NotFoundError("we do not stock that catalog number", catalog=wanted)
        return Instrument(
            catalog=rows.get_text(row, "catalog"),
            description=rows.get_text(row, "description"),
            manufacturer=rows.get_text(row, "manufacturer"),
            material=material_named(rows.get_text(row, "material")),
            complexity=rows.get_enum(row, "complexity", Complexity),
            criticality=rows.get_enum(row, "criticality", Criticality),
            lumen_diameter_mm=_optional_float(row["lumen_mm"]),
            lumen_length_mm=_optional_float(row["lumen_len_mm"]),
            requires_disassembly=rows.get_bool(row, "disassembly"),
            insulated=rows.get_bool(row, "insulated"),
            weight=rows.get_mass_or_none(row, "weight_g"),
        )

    def instruments(self) -> tuple[Instrument, ...]:
        found = self.db.query("SELECT catalog FROM instrument ORDER BY catalog")
        return tuple(self.instrument(str(row["catalog"])) for row in found)

    def stocks(self, catalog: str) -> bool:
        wanted = catalog_number(catalog)
        return self.db.scalar("SELECT 1 FROM instrument WHERE catalog = ?", [wanted]) is not None

    def save_history(self, history: RevisionHistory) -> None:
        """Write every revision of a sheet, replacing what is there."""
        with self.db.transaction():
            self.db.execute("DELETE FROM sheet_line WHERE code = ?", [history.code])
            self.db.execute("DELETE FROM sheet WHERE code = ?", [history.code])
            for revision in history.revisions:
                self._save_revision(revision)

    def _save_revision(self, revision: Revision) -> None:
        sheet = revision.sheet
        self.db.execute(
            "INSERT INTO sheet (code, revision, name, container, starts_on, ends_on, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                sheet.code,
                revision.number,
                sheet.name,
                sheet.container,
                rows.put_date(revision.effective.start),
                rows.put_date(revision.effective.end),
                revision.note,
            ],
        )
        self.db.execute_many(
            "INSERT INTO sheet_line (code, revision, catalog, quantity, position, required)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                [
                    sheet.code,
                    revision.number,
                    line.catalog,
                    line.quantity,
                    line.position,
                    rows.put_bool(line.required),
                ]
                for line in sheet.lines
            ],
        )

    def history(self, code: str) -> RevisionHistory:
        wanted = tray_code(code)
        found = self.db.query(
            "SELECT code, revision, name, container, starts_on, ends_on, note FROM sheet"
            " WHERE code = ? ORDER BY revision",
            [wanted],
        )
        if not found:
            raise NotFoundError("no set with that code", code=wanted)
        revisions = tuple(self._revision(row) for row in found)
        return RevisionHistory(wanted, revisions)

    def _revision(self, row: object) -> Revision:
        assert hasattr(row, "keys")
        code = rows.get_text(row, "code")  # type: ignore[arg-type]
        number = rows.get_int(row, "revision")  # type: ignore[arg-type]
        lines = self.db.query(
            "SELECT catalog, quantity, position, required FROM sheet_line"
            " WHERE code = ? AND revision = ? ORDER BY catalog",
            [code, number],
        )
        sheet = CountSheet.of(
            code,
            rows.get_text(row, "name"),  # type: ignore[arg-type]
            [
                CountLine(
                    self.instrument(rows.get_text(line, "catalog")),
                    rows.get_int(line, "quantity"),
                    rows.get_text_or_empty(line, "position"),
                    rows.get_bool(line, "required"),
                )
                for line in lines
            ],
            row["container"],  # type: ignore[index]
        )
        window = DateRange(
            rows.get_date(row, "starts_on"),  # type: ignore[arg-type]
            rows.get_date_or_none(row, "ends_on"),  # type: ignore[arg-type]
        )
        return Revision(number, sheet, window, rows.get_text_or_empty(row, "note"))  # type: ignore[arg-type]

    def sheet(self, code: str, day: date) -> CountSheet:
        return self.history(code).at(day).sheet

    def set_codes(self) -> tuple[str, ...]:
        found = self.db.query("SELECT DISTINCT code FROM sheet ORDER BY code")
        return tuple(str(row["code"]) for row in found)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]
