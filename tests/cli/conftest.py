"""Shared helpers for the command line tests.

Every one of these files was building the same department: a chamber, a tray, a
cycle and a passing air removal test. Four copies of that setup is four places
to update when a required option changes, so it lives here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sterilot.cli.main import main

BADGE = "T-4471"


def invoke(db: str, *args: str, badge: str | None = BADGE, migrate: bool = True) -> Result:
    """Run a command against ``db``, signed unless ``badge`` is None."""
    prefix = ["--db", db]
    if badge is not None:
        prefix.extend(["--badge", badge])
    if not migrate:
        prefix.append("--no-migrate")
    return CliRunner().invoke(main, [*prefix, *args])


def add_sterilizer(db: str, equipment: str = "AC-1", *extra: str) -> Result:
    return invoke(
        db,
        "machine",
        "add-sterilizer",
        equipment,
        "--model",
        "Amsco 400",
        "--manufacturer",
        "Steris",
        "--method",
        "prevac",
        *extra,
    )


def add_washer(db: str, equipment: str = "WD-2", *extra: str) -> Result:
    return invoke(
        db,
        "machine",
        "add-washer",
        equipment,
        "--model",
        "Reliance 444",
        "--manufacturer",
        "Steris",
        "--qualified",
        "2025-01-02",
        *extra,
    )


def record_cycle(db: str, started: str, run: int | None = None, equipment: str = "AC-1") -> Result:
    args = [
        "cycle",
        "record",
        "--equipment",
        equipment,
        "--method",
        "prevac",
        "--started",
        started,
        "--temp",
        "133.4C",
        "--exposure",
        "4",
        "--dry",
        "31",
        "--pulses",
        "4",
        "--pressure",
        "29.6 psig",
    ]
    if run is not None:
        args.extend(["--run", str(run)])
    return invoke(db, *args)


ASSEMBLY_ROUTE = ("decontamination", "clean", "assembled")


def assemble(db: str, asset: str, code: str = "ORT-MAJOR") -> None:
    """Register a tray and walk it to the assembly bench, ready for a load."""
    invoke(db, "tray", "register", asset, code)
    for stage in ASSEMBLY_ROUTE:
        invoke(db, "tray", "move", asset, stage)


@pytest.fixture
def db(tmp_path: Path) -> str:
    """An empty database with no machines in it."""
    return str(tmp_path / "sterilot.sqlite3")


@pytest.fixture
def ready(db: str) -> str:
    """A chamber, two trays, a cycle and a passing air removal test."""
    add_sterilizer(db)
    assemble(db, "ORT-0114")
    assemble(db, "IMP-0001", "IMP-KNEE")
    record_cycle(db, "2025-01-14 08:00")
    invoke(db, "duty", "log", "AC-1", "air removal", "--on", "2025-01-14")
    return db
