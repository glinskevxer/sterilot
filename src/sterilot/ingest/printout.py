"""Reading a steam sterilizer printout.

The printer on a hospital sterilizer produces a narrow paper tape with a fixed
set of labelled lines and a lot of whitespace. It has not changed since the
nineteen nineties and it is not going to, so parsing it is a matter of knowing
the labels rather than anything clever.

What comes out is a printout object with the raw labelled values kept as they
were, and a conversion into the measurements the release engine wants. Keeping
both means a value we cannot interpret is still visible to whoever has to look
at the tape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sterilot.clock import parse_moment
from sterilot.errors import ValidationError
from sterilot.ids import LotControlNumber, badge_number, equipment_id
from sterilot.sterilizer.parameters import CycleMeasurements
from sterilot.units.duration import Duration
from sterilot.units.pressure import Pressure
from sterilot.units.temperature import Temperature

_LABEL = re.compile(r"^\s*(?P<label>[A-Z][A-Z0-9 ./#]*?)\s{2,}(?P<value>\S.*?)\s*$")
_DATE_TIME = re.compile(
    r"DATE\s+(?P<date>\S+)\s+TIME\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)", re.IGNORECASE
)
_ABORT = re.compile(r"^\s*(?:CYCLE\s+)?ABORT(?:ED)?\s*[-:]?\s*(?P<reason>.*?)\s*$", re.IGNORECASE)

_ALIASES = {
    "STERILIZER": "equipment",
    "UNIT": "equipment",
    "CYCLE": "cycle_name",
    "CYCLE NO": "run",
    "CYCLE #": "run",
    "OPERATOR": "operator",
    "STER TEMP": "hold_temperature",
    "STERILIZE TEMP": "hold_temperature",
    "STER TIME": "exposure",
    "STERILIZE TIME": "exposure",
    "DRY TIME": "dry_time",
    "CHAMBER PRESSURE": "pressure",
    "STER PRESS": "pressure",
    "PULSES": "pulses",
    "CONDITIONING PULSES": "pulses",
    "MAX TEMP": "max_temperature",
    "MIN TEMP": "min_temperature",
}


@dataclass(frozen=True)
class Printout:
    """One tape, read."""

    equipment: str
    cycle_name: str
    run: int
    started_at: datetime
    operator: str
    values: dict[str, str]
    complete: bool = True
    abort_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", equipment_id(self.equipment))
        object.__setattr__(self, "operator", badge_number(self.operator))
        if self.run < 1:
            raise ValidationError("cycle numbers start at one", run=self.run)

    @property
    def aborted(self) -> bool:
        return not self.complete

    def lot(self) -> LotControlNumber:
        return LotControlNumber(self.equipment, self.started_at.date(), self.run)

    def measurements(self) -> CycleMeasurements:
        """Turn the labelled values into what the cycle record wants."""
        hold = self.values.get("hold_temperature")
        exposure = self.values.get("exposure")
        if hold is None or exposure is None:
            raise ValidationError(
                "the tape has no sterilize temperature or time", equipment=self.equipment
            )
        pressure = self.values.get("pressure")
        pulses = self.values.get("pulses")
        return CycleMeasurements(
            hold_temperature=Temperature.parse(hold),
            exposure=Duration.parse(exposure, bare_unit="m"),
            dry_time=Duration.parse(self.values.get("dry_time", "0"), bare_unit="m"),
            chamber_pressure=_pressure(pressure) if pressure else None,
            conditioning_pulses=int(pulses) if pulses and pulses.isdigit() else None,
        )


def _pressure(text: str) -> Pressure:
    cleaned = text.strip().upper()
    number = re.match(r"^[-+]?\d+(?:\.\d+)?", cleaned)
    if number is None:
        raise ValidationError("cannot read that as a pressure", text=text)
    value = float(number.group())
    if "PSIG" in cleaned:
        return Pressure.from_psig(value)
    if "PSIA" in cleaned or "PSI" in cleaned:
        return Pressure.from_psia(value)
    if "BAR" in cleaned:
        return Pressure.from_bar_absolute(value)
    return Pressure.from_kpa_absolute(value)


def parse_printout(text: str) -> Printout:
    """Read a tape into a :class:`Printout`."""
    if not text.strip():
        raise ValidationError("the tape is empty")
    labelled: dict[str, str] = {}
    started_at: datetime | None = None
    complete = False
    abort_reason = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stamp = _DATE_TIME.search(stripped)
        if stamp is not None:
            started_at = _moment(stamp.group("date"), stamp.group("time"))
            continue
        if stripped.upper().startswith("CYCLE COMPLETE"):
            complete = True
            continue
        abort = _ABORT.match(stripped)
        if abort is not None and "ABORT" in stripped.upper():
            complete = False
            abort_reason = abort.group("reason") or "no reason printed"
            continue
        match = _LABEL.match(line)
        if match is None:
            continue
        label = " ".join(match.group("label").split()).upper()
        key = _ALIASES.get(label)
        if key is not None:
            labelled[key] = match.group("value").strip()
    if started_at is None:
        raise ValidationError("the tape has no date and time")
    for needed in ("equipment", "run", "operator"):
        if needed not in labelled:
            raise ValidationError("the tape is missing a field", field=needed)
    run = labelled.pop("run")
    if not run.isdigit():
        raise ValidationError("the cycle number is not a number", run=run)
    return Printout(
        equipment=labelled.pop("equipment"),
        cycle_name=labelled.pop("cycle_name", ""),
        run=int(run),
        started_at=started_at,
        operator=labelled.pop("operator"),
        values=labelled,
        complete=complete,
        abort_reason=abort_reason,
    )


def _moment(day: str, clock: str) -> datetime:
    return parse_moment(f"{day} {clock}")
