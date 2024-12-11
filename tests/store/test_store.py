from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from sterilot.catalog.instrument import Instrument
from sterilot.catalog.material import material_named
from sterilot.errors import IntegrityError
from sterilot.methods import Method
from sterilot.quality.audit import Action
from sterilot.store.cycle_repo import standard_spec
from sterilot.store.db import Database
from sterilot.store.migrations import MIGRATIONS, latest_version
from sterilot.store.store import Store


def test_an_in_memory_store_is_migrated_and_healthy() -> None:
    with Store.in_memory() as store:
        assert store.up_to_date
        assert store.version == latest_version()
        assert store.health() == ()


def test_the_repositories_share_one_connection() -> None:
    with Store.in_memory() as store:
        assert store.catalog.db is store.db
        assert store.loads.cycles is store.cycles
        assert store.trays.db is store.db


def test_a_file_store_persists_between_opens(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as store:
        store.catalog.save_instrument(
            Instrument("SU-1234", "forceps", "V Mueller", material_named("SS"))
        )
    with Store.open(path) as store:
        assert store.catalog.stocks("SU-1234")


def test_opening_without_migrating_leaves_the_file_alone(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path, apply_migrations=False) as store:
        assert store.version == 0
        assert not store.up_to_date
        assert any("version 0" in item for item in store.health())


def test_a_database_from_a_newer_build_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path):
        pass
    db = Database.open(path)
    db.execute(
        "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
        [99, datetime(2025, 1, 1).isoformat(), "from the future"],
    )
    db.close()
    with pytest.raises(IntegrityError):
        Store.open(path)


def test_the_migration_time_can_be_pinned(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path, now=datetime(2024, 12, 15, 9, 0)) as store:
        row = store.db.require_one("SELECT applied_at FROM schema_version WHERE version = 1")
        assert row["applied_at"] == "2024-12-15T09:00:00"


def test_a_broken_audit_chain_shows_up_in_health() -> None:
    with Store.in_memory() as store:
        store.quality.record(
            datetime(2024, 12, 10, 9, 0), "T-4471", Action.RECORDED, "load", "LD-1"
        )
        store.db.execute("UPDATE audit_event SET detail = 'edited' WHERE sequence = 1")
        assert store.health() == ()
        store.db.execute("UPDATE audit_event SET previous = 'x' WHERE sequence = 1")
        assert "the audit trail has a break in it" in store.health()


def test_a_dangling_reference_shows_up_in_health() -> None:
    with Store.in_memory() as store:
        store.db.execute("PRAGMA foreign_keys = OFF")
        store.db.execute(
            "INSERT INTO sheet (code, revision, name, starts_on) VALUES (?, ?, ?, ?)",
            ["ORT-MAJOR", 1, "ortho", "2024-01-01"],
        )
        store.db.execute(
            "INSERT INTO sheet_line (code, revision, catalog, quantity) VALUES (?, ?, ?, ?)",
            ["ORT-MAJOR", 1, "SU-9999", 1],
        )
        problems = store.health()
        assert any("breaks a reference" in item for item in problems)


def test_a_department_spec_resolver_reaches_the_cycle_store() -> None:
    with Store.in_memory(resolve_spec=lambda name, method: standard_spec(name, method)) as store:
        assert store.cycles.resolve_spec("PREVAC-132", Method.STEAM_PREVAC).name == "PREVAC-132"


def test_every_migration_lands_when_the_store_opens() -> None:
    with Store.in_memory() as store:
        rows = store.db.query("SELECT version FROM schema_version ORDER BY version")
        assert [row["version"] for row in rows] == [item.version for item in MIGRATIONS]


def test_the_store_closes_its_database() -> None:
    store = Store.in_memory()
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        store.db.execute("SELECT 1")


def test_a_saved_cycle_is_readable_through_the_load_store() -> None:
    with Store.in_memory() as store:
        store.cycles.register_equipment("AC-1", "sterilizer", "Amsco", "Steris")
        assert store.cycles.next_run("AC-1", date(2024, 12, 15)) == 1
