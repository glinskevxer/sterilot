"""What every command needs to hand.

The store, the department's settings, a clock and the badge of whoever is
running the command. The badge is not decoration: nearly every write in this
system is signed, and a command that cannot say who ran it should not be able
to write anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sterilot.clock import Clock
from sterilot.errors import ConfigurationError
from sterilot.ids import badge_number
from sterilot.settings import Settings
from sterilot.store.store import Store

DB_ENV = "STERILOT_DB"
BADGE_ENV = "STERILOT_BADGE"
DEFAULT_DB = "sterilot.sqlite3"


def default_db_path() -> Path:
    return Path(os.environ.get(DB_ENV, DEFAULT_DB))


def default_badge() -> str | None:
    found = os.environ.get(BADGE_ENV)
    return found or None


@dataclass
class Context:
    """The handle every command works through."""

    store: Store
    settings: Settings
    clock: Clock
    badge: str | None = None

    @classmethod
    def build(
        cls,
        db_path: Path | str | None = None,
        settings_path: Path | None = None,
        badge: str | None = None,
        clock: Clock | None = None,
        apply_migrations: bool = True,
    ) -> Context:
        store = Store.open(db_path or default_db_path(), apply_migrations=apply_migrations)
        settings = Settings.load_or_default(settings_path)
        chosen = badge or default_badge()
        return cls(store, settings, clock or Clock(), badge_number(chosen) if chosen else None)

    def signed_by(self) -> str:
        """The badge, or a clear refusal rather than an anonymous write."""
        if self.badge is None:
            raise ConfigurationError(
                "that command writes a record, so it needs a badge",
                hint=f"pass --badge or set {BADGE_ENV}",
            )
        return self.badge

    def now(self) -> datetime:
        return self.clock.now()

    def close(self) -> None:
        self.store.close()
