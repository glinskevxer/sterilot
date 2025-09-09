"""The error hierarchy.

Every failure in the package is one of these. The CLI maps ``exit_status`` onto
its own exit code, so a caller that scripts against sterilot can tell a missing
record apart from a rule that refused the operation without parsing text.
"""

from __future__ import annotations

from typing import Any


class SterilotError(Exception):
    """Base class for everything raised on purpose."""

    code = "sterilot_error"
    exit_status = 1

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:
        if not self.context:
            return self.message
        return f"{self.message} ({self.context_text()})"

    def context_text(self) -> str:
        """The context rendered as ``key=value`` pairs in insertion order."""
        return ", ".join(f"{key}={value!r}" for key, value in self.context.items())

    def describe(self) -> dict[str, Any]:
        """A dict shaped for structured output."""
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class ValidationError(SterilotError):
    """A value did not survive its own constructor."""

    code = "validation"
    exit_status = 2


class NotFoundError(SterilotError):
    """A record was looked up by key and is not there."""

    code = "not_found"
    exit_status = 3


class ConflictError(SterilotError):
    """A record already exists, or the state transition is not available."""

    code = "conflict"
    exit_status = 4


class PolicyError(SterilotError):
    """A departmental rule refused the operation.

    This is the interesting one. A load that cannot be released, a tray issued
    past its event related sterility, a technician without the competency to
    sign a cycle: none of those are bad input, they are the department saying
    no.
    """

    code = "policy"
    exit_status = 5


class IntegrityError(SterilotError):
    """The stored data contradicts itself."""

    code = "integrity"
    exit_status = 6


class ConfigurationError(SterilotError):
    """The department is set up in a way the code cannot work with."""

    code = "configuration"
    exit_status = 7


MEANINGS = {
    "sterilot_error": "something went wrong",
    "validation": "bad input",
    "not_found": "not found",
    "conflict": "a state conflict",
    "policy": "a rule refused it",
    "integrity": "the stored data contradicts itself",
    "configuration": "a setup problem",
}


def meaning(error: SterilotError) -> str:
    """The one line explanation that goes with an exit status."""
    return MEANINGS.get(error.code, MEANINGS["sterilot_error"])


def require(condition: bool, message: str, **context: Any) -> None:
    """Raise :class:`ValidationError` when ``condition`` is false."""
    if not condition:
        raise ValidationError(message, **context)


def refuse(message: str, **context: Any) -> None:
    """Raise :class:`PolicyError` unconditionally.

    Reads better than ``raise`` at the end of a long chain of rule checks.
    """
    raise PolicyError(message, **context)
