"""Department settings.

Everything in here is a number a supervisor can defend to an inspector, which
is why none of them are constants buried in the module that uses them. A
different hospital runs different numbers and the code should not care.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sterilot.errors import ConfigurationError, ValidationError

DEFAULT_FILENAME = "sterilot.toml"

NOTES = {
    "facility": "the name that goes at the top of every report",
    "set_weight_limit_kg": "a set over this will not dry, container and contents together",
    "shelf_life_days": "leave this out for event related sterility, which is the default",
    "bi_incubation_hours": "how long a biological sits before anybody may read it",
    "implant_hold_required": "hold an implant load until its biological is read",
    "emergency_release_allowed": "allow a documented early release on a held load",
    "loaner_lead_hours": "how far ahead of a case a vendor set has to arrive",
    "wet_pack_rejects_load": "a wet load is rejected rather than dried and released",
    "max_daily_runs": "the highest run number a lot control number may carry in a day",
    "cooling_minutes": "how long a load cools before anybody touches it",
}


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


@dataclass(frozen=True)
class Settings:
    """The knobs the department is allowed to turn."""

    facility: str = "Central Service"
    set_weight_limit_kg: float = 11.4
    shelf_life_days: int | None = None
    bi_incubation_hours: float = 24.0
    implant_hold_required: bool = True
    emergency_release_allowed: bool = True
    loaner_lead_hours: int = 48
    wet_pack_rejects_load: bool = True
    max_daily_runs: int = 24
    cooling_minutes: int = 30

    def __post_init__(self) -> None:
        if not self.facility.strip():
            raise ValidationError("facility name is empty")
        if self.set_weight_limit_kg <= 0:
            raise ValidationError(
                "set weight limit must be positive", value=self.set_weight_limit_kg
            )
        if self.shelf_life_days is not None and self.shelf_life_days <= 0:
            raise ValidationError(
                "shelf life must be positive or absent", value=self.shelf_life_days
            )
        if self.bi_incubation_hours <= 0:
            raise ValidationError(
                "incubation time must be positive", value=self.bi_incubation_hours
            )
        if self.loaner_lead_hours < 0:
            raise ValidationError(
                "loaner lead time cannot be negative", value=self.loaner_lead_hours
            )
        if not 1 <= self.max_daily_runs <= 99:
            raise ValidationError("daily run ceiling is out of range", value=self.max_daily_runs)
        if self.cooling_minutes < 0:
            raise ValidationError("cooling time cannot be negative", value=self.cooling_minutes)

    @property
    def event_related_sterility(self) -> bool:
        """True when packages expire on an event rather than on a date."""
        return self.shelf_life_days is None

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> Settings:
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - known)
        if unknown:
            raise ConfigurationError("settings we do not recognise", keys=unknown)
        return cls(**values)

    @classmethod
    def load(cls, path: Path) -> Settings:
        """Read a settings file. A missing file is a configuration error."""
        if not path.exists():
            raise ConfigurationError("no settings file there", path=str(path))
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError("settings file will not parse", path=str(path)) from exc
        section = raw.get("sterilot", raw)
        if not isinstance(section, dict):
            raise ConfigurationError("the sterilot section is not a table", path=str(path))
        return cls.from_mapping(section)

    @classmethod
    def load_or_default(cls, path: Path | None) -> Settings:
        if path is None:
            return cls()
        return cls.load(path)

    def with_values(self, **values: Any) -> Settings:
        return replace(self, **values)

    def describe(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    def to_toml(self) -> str:
        """The current settings as a file a supervisor can edit.

        Written out with the note beside each value rather than a bare table,
        because a number nobody can explain gets changed by whoever is on shift
        when it first gets in the way.
        """
        lines = ["[sterilot]"]
        for field in self.__dataclass_fields__:
            note = NOTES.get(field)
            if note:
                lines.append(f"# {note}")
            value = getattr(self, field)
            if value is None:
                lines.append(f"# {field} is not set")
            else:
                lines.append(f"{field} = {_toml_value(value)}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
