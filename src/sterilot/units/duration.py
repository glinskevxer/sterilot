"""Durations, because every printer writes them differently.

The steam sterilizer prints ``00:04:00``, the washer export writes ``240`` and
means seconds, the low temperature unit writes ``47 min``. All of it becomes a
:class:`Duration`, which is seconds and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sterilot.errors import ValidationError

_CLOCK = re.compile(r"^\s*(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{1,2}(?:\.\d+)?)\s*$")
_SPELLED = re.compile(
    r"^\s*(?:(?P<h>\d+(?:\.\d+)?)\s*h(?:r|rs|our|ours)?)?\s*"
    r"(?:(?P<m>\d+(?:\.\d+)?)\s*m(?:in|ins|inute|inutes)?)?\s*"
    r"(?:(?P<s>\d+(?:\.\d+)?)\s*s(?:ec|ecs|econd|econds)?)?\s*$"
)
_BARE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True, order=True)
class Duration:
    """A length of time in seconds. Never negative."""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ValidationError("a duration cannot run backwards", seconds=self.seconds)

    @classmethod
    def of_seconds(cls, value: float) -> Duration:
        return cls(float(value))

    @classmethod
    def of_minutes(cls, value: float) -> Duration:
        return cls(float(value) * 60.0)

    @classmethod
    def of_hours(cls, value: float) -> Duration:
        return cls(float(value) * 3600.0)

    @classmethod
    def zero(cls) -> Duration:
        return cls(0.0)

    @classmethod
    def parse(cls, text: str, bare_unit: str = "s") -> Duration:
        """Read a clock string, a spelled string, or a bare number.

        A bare number has no unit in it, so the caller says what the source
        meant with ``bare_unit``. The washer export means seconds, the paper
        cycle log means minutes.
        """
        clock = _CLOCK.match(text)
        if clock is not None:
            hours = float(clock.group("h") or 0)
            minutes = float(clock.group("m"))
            seconds = float(clock.group("s"))
            if minutes >= 60 or seconds >= 60:
                raise ValidationError("clock time has a field over 59", text=text)
            return cls(hours * 3600.0 + minutes * 60.0 + seconds)
        bare = _BARE.match(text)
        if bare is not None:
            value = float(bare.group("value"))
            if bare_unit == "s":
                return cls(value)
            if bare_unit == "m":
                return cls.of_minutes(value)
            if bare_unit == "h":
                return cls.of_hours(value)
            raise ValidationError("unknown bare unit", bare_unit=bare_unit)
        spelled = _SPELLED.match(text)
        if spelled is not None and any(spelled.group(part) for part in ("h", "m", "s")):
            return cls(
                float(spelled.group("h") or 0) * 3600.0
                + float(spelled.group("m") or 0) * 60.0
                + float(spelled.group("s") or 0)
            )
        raise ValidationError("cannot read that as a duration", text=text)

    @property
    def minutes(self) -> float:
        return self.seconds / 60.0

    @property
    def hours(self) -> float:
        return self.seconds / 3600.0

    def __add__(self, other: Duration) -> Duration:
        return Duration(self.seconds + other.seconds)

    def __sub__(self, other: Duration) -> Duration:
        return Duration(self.seconds - other.seconds)

    def __mul__(self, factor: float) -> Duration:
        return Duration(self.seconds * factor)

    def __bool__(self) -> bool:
        return self.seconds > 0

    def shortfall_against(self, floor: Duration) -> Duration:
        """How much short of ``floor`` this duration is, zero when it clears."""
        if self.seconds >= floor.seconds:
            return Duration.zero()
        return Duration(floor.seconds - self.seconds)

    def clamp(self, low: Duration, high: Duration) -> Duration:
        if low.seconds > high.seconds:
            raise ValidationError("clamp bounds are the wrong way round")
        return Duration(min(max(self.seconds, low.seconds), high.seconds))

    def rounded(self, places: int = 0) -> Duration:
        return Duration(round(self.seconds, places))

    def clock(self) -> str:
        """``h:mm:ss`` the way the sterilizer prints it."""
        whole = int(round(self.seconds))
        hours, rest = divmod(whole, 3600)
        minutes, seconds = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    def spelled(self) -> str:
        """``4m 12s``, which is what a technician writes on the log."""
        whole = int(round(self.seconds))
        hours, rest = divmod(whole, 3600)
        minutes, seconds = divmod(rest, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)

    def __str__(self) -> str:
        return self.spelled()


def total(durations: Iterable[Duration]) -> Duration:
    """Sum of an iterable, zero when it is empty."""
    return Duration(sum(item.seconds for item in durations))


def longest(durations: Iterable[Duration]) -> Duration:
    values = list(durations)
    if not values:
        raise ValidationError("no durations to take a maximum of")
    return max(values)
