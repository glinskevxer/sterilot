"""The catalog as one object: items, sheets and approvals together.

Each of the three is fine on its own and they only mean something together. A
count sheet line pointing at a catalog number nobody stocks is the kind of
thing that reads fine for a year and then strands a tray at two in the morning,
so the registry can be asked to check itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sterilot.catalog.instrument import Instrument
from sterilot.catalog.revision import RevisionHistory
from sterilot.catalog.substitution import SubstitutionTable
from sterilot.catalog.tray import CountSheet
from sterilot.errors import ConflictError, NotFoundError
from sterilot.ids import catalog_number, tray_code
from sterilot.methods import Method


@dataclass(frozen=True)
class Catalog:
    """Everything the department stocks and every set it builds."""

    instruments: dict[str, Instrument] = field(default_factory=dict)
    histories: dict[str, RevisionHistory] = field(default_factory=dict)
    substitutions: SubstitutionTable = field(default_factory=SubstitutionTable)

    @classmethod
    def build(
        cls,
        instruments: Iterable[Instrument] = (),
        histories: Iterable[RevisionHistory] = (),
        substitutions: SubstitutionTable | None = None,
    ) -> Catalog:
        by_catalog: dict[str, Instrument] = {}
        for item in instruments:
            if item.catalog in by_catalog:
                raise ConflictError("that catalog number is stocked twice", catalog=item.catalog)
            by_catalog[item.catalog] = item
        by_code: dict[str, RevisionHistory] = {}
        for history in histories:
            if history.code in by_code:
                raise ConflictError("that set code is defined twice", code=history.code)
            by_code[history.code] = history
        return cls(by_catalog, by_code, substitutions or SubstitutionTable())

    def instrument(self, catalog: str) -> Instrument:
        wanted = catalog_number(catalog)
        if wanted not in self.instruments:
            raise NotFoundError("we do not stock that catalog number", catalog=wanted)
        return self.instruments[wanted]

    def stocks(self, catalog: str) -> bool:
        return catalog_number(catalog) in self.instruments

    def history(self, code: str) -> RevisionHistory:
        wanted = tray_code(code)
        if wanted not in self.histories:
            raise NotFoundError("no set with that code", code=wanted)
        return self.histories[wanted]

    def sheet(self, code: str, day: date) -> CountSheet:
        """The sheet that was in force on ``day``."""
        return self.history(code).at(day).sheet

    def current_sheet(self, code: str) -> CountSheet:
        return self.history(code).current.sheet

    def set_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self.histories))

    def sets_containing(self, catalog: str, day: date) -> tuple[str, ...]:
        """Which sets called for an item on a given day."""
        wanted = catalog_number(catalog)
        found: list[str] = []
        for code, history in self.histories.items():
            try:
                sheet = history.at(day).sheet
            except NotFoundError:
                continue
            if sheet.holds(wanted):
                found.append(code)
        return tuple(sorted(found))

    def sets_for_method(self, method: Method, day: date) -> tuple[str, ...]:
        found: list[str] = []
        for code, history in self.histories.items():
            try:
                sheet = history.at(day).sheet
            except NotFoundError:
                continue
            if sheet.tolerates(method):
                found.append(code)
        return tuple(sorted(found))

    def problems(self, day: date) -> tuple[str, ...]:
        """Every inconsistency between the three parts, worst first."""
        found: list[str] = []
        for code in sorted(self.histories):
            history = self.histories[code]
            try:
                sheet = history.at(day).sheet
            except NotFoundError:
                continue
            for line in sheet.lines:
                if not self.stocks(line.catalog):
                    found.append(f"{code} calls for {line.catalog}, which we do not stock")
            if not sheet.methods():
                found.append(f"{code} has no sterilization method its contents all tolerate")
        for entry in self.substitutions.active(day):
            if not self.stocks(entry.original):
                found.append(f"substitution names {entry.original}, which we do not stock")
            if not self.stocks(entry.replacement):
                found.append(f"substitution offers {entry.replacement}, which we do not stock")
        return tuple(found)

    def with_instrument(self, item: Instrument) -> Catalog:
        if item.catalog in self.instruments:
            raise ConflictError("that catalog number is stocked twice", catalog=item.catalog)
        return Catalog(
            {**self.instruments, item.catalog: item}, dict(self.histories), self.substitutions
        )

    def with_history(self, history: RevisionHistory) -> Catalog:
        return Catalog(
            dict(self.instruments),
            {**self.histories, history.code: history},
            self.substitutions,
        )

    def with_substitutions(self, substitutions: SubstitutionTable) -> Catalog:
        return Catalog(dict(self.instruments), dict(self.histories), substitutions)
