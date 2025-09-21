"""Sterile processing records for a hospital central service department.

The package is organised by what a thing is rather than by what layer it sits
in: ``catalog`` is what the department owns, ``decon`` and ``sterilizer`` are
the machines and what they did, ``load`` is the decision the whole record
exists to support, ``store`` is the file it all lives in, and ``cli`` is how
anybody actually uses it.

What is exported here is the handful of names an embedding application needs:
the store, the settings, the clock and the error hierarchy. Everything else is
imported from the module it belongs to, so a reader can tell where a name comes
from without a table of contents.
"""

from __future__ import annotations

from sterilot.clock import Clock
from sterilot.errors import (
    ConfigurationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    PolicyError,
    SterilotError,
    ValidationError,
)
from sterilot.settings import Settings

__version__ = "1.0.0"

__all__ = [
    "Clock",
    "ConfigurationError",
    "ConflictError",
    "IntegrityError",
    "NotFoundError",
    "PolicyError",
    "Settings",
    "SterilotError",
    "ValidationError",
    "__version__",
]


def open_store(path: str) -> object:
    """Open the department's database, migrating it if it is behind.

    A thin wrapper so an embedding application does not have to know which
    module the store lives in. Imported lazily because the store pulls in every
    repository, and something that only wants the error types should not pay
    for that.
    """
    from sterilot.store.store import Store

    return Store.open(path)
