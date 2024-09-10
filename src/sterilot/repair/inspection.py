"""The assembly bench inspection, which is the last chance to catch anything.

Every instrument is looked at under magnification before it goes back in a
tray, and what is looked for depends on what the instrument is. A hinged
forceps has a box lock that can seize. A scissor has an edge that goes dull. A
bipolar has insulation that cracks and will burn a patient somewhere the
surgeon is not looking.

So the checklist is derived from the catalog entry rather than being one list
everybody skims. An instrument with no lumen does not need a lumen check, and
an instrument with insulation cannot be signed off without one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sterilot.catalog.instrument import Complexity, Instrument
from sterilot.errors import ValidationError
from sterilot.ids import asset_tag, badge_number, catalog_number


class Check(Enum):
    """One thing the technician looks for."""

    CLEANLINESS = "cleanliness"
    CORROSION = "corrosion"
    FUNCTION = "function"
    ALIGNMENT = "alignment"
    SHARPNESS = "sharpness"
    LUMEN = "lumen"
    INSULATION = "insulation"
    COMPLETENESS = "completeness"

    @property
    def label(self) -> str:
        return self.value

    @property
    def universal(self) -> bool:
        """Checks every instrument gets, whatever it is."""
        return self in {Check.CLEANLINESS, Check.CORROSION}

    @classmethod
    def named(cls, value: str) -> Check:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such check", value=value)


class Finding(Enum):
    """What the technician saw."""

    PASS = "pass"
    MINOR = "minor"
    FAIL = "fail"

    @property
    def blocking(self) -> bool:
        """A minor finding is written down and the tray still goes out."""
        return self is Finding.FAIL

    @classmethod
    def named(cls, value: str) -> Finding:
        wanted = value.strip().lower()
        for member in cls:
            if wanted == member.value:
                return member
        raise ValidationError("no such finding", value=value)


def checks_for(item: Instrument) -> tuple[Check, ...]:
    """The checklist this catalog entry earns."""
    wanted: list[Check] = [check for check in Check if check.universal]
    if item.complexity in {Complexity.HINGED, Complexity.MULTIPART, Complexity.POWERED}:
        wanted.append(Check.FUNCTION)
        wanted.append(Check.ALIGNMENT)
    if "scissor" in item.description.lower() or "rongeur" in item.description.lower():
        wanted.append(Check.SHARPNESS)
    if item.has_lumen:
        wanted.append(Check.LUMEN)
    if item.insulated:
        wanted.append(Check.INSULATION)
    if item.requires_disassembly:
        wanted.append(Check.COMPLETENESS)
    return tuple(sorted(set(wanted), key=lambda check: list(Check).index(check)))


@dataclass(frozen=True)
class CheckResult:
    """One check on one instrument."""

    check: Check
    finding: Finding
    note: str = ""

    def __post_init__(self) -> None:
        if self.finding is not Finding.PASS and not self.note.strip():
            raise ValidationError("a finding is written down", check=self.check.value)

    def describe(self) -> str:
        if self.finding is Finding.PASS:
            return f"{self.check.label} pass"
        return f"{self.check.label} {self.finding.value}: {self.note}"


@dataclass(frozen=True)
class Inspection:
    """One instrument, inspected at the bench."""

    asset: str
    catalog: str
    at: datetime
    by: str
    results: tuple[CheckResult, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", asset_tag(self.asset))
        object.__setattr__(self, "catalog", catalog_number(self.catalog))
        object.__setattr__(self, "by", badge_number(self.by))
        seen = [result.check for result in self.results]
        if len(set(seen)) != len(seen):
            raise ValidationError("the same check is recorded twice", asset=self.asset)

    @classmethod
    def of(
        cls, asset: str, catalog: str, at: datetime, by: str, results: Iterable[CheckResult]
    ) -> Inspection:
        return cls(asset, catalog, at, by, tuple(results))

    def result_for(self, check: Check) -> CheckResult | None:
        for result in self.results:
            if result.check is check:
                return result
        return None

    def problems(self, item: Instrument) -> tuple[str, ...]:
        """Missing checks and failed ones, in checklist order."""
        if item.catalog != self.catalog:
            raise ValidationError(
                "that inspection is for a different item",
                inspection=self.catalog,
                item=item.catalog,
            )
        found: list[str] = []
        for check in checks_for(item):
            result = self.result_for(check)
            if result is None:
                found.append(f"{check.label} was not checked")
            elif result.finding.blocking:
                found.append(f"{check.label} failed: {result.note}")
        return tuple(found)

    def minor_findings(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if result.finding is Finding.MINOR)

    def passed(self, item: Instrument) -> bool:
        return not self.problems(item)
