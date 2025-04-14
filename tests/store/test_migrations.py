from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ConflictError, IntegrityError
from sterilot.store.db import Database
from sterilot.store.migrations import (
    MIGRATIONS,
    applied,
    current_version,
    ensure_current,
    latest_version,
    migrate,
    pending,
    problems,
)

NOW = datetime(2024, 11, 1, 9, 0)


def test_a_fresh_database_is_at_version_zero() -> None:
    with Database.in_memory() as db:
        assert current_version(db) == 0
        assert applied(db) == ()
        assert len(pending(db)) == len(MIGRATIONS)


def test_migrating_applies_everything_in_order() -> None:
    with Database.in_memory() as db:
        done = migrate(db, NOW)
        assert [item.version for item in done] == [item.version for item in MIGRATIONS]
        assert current_version(db) == latest_version()
        assert pending(db) == ()


def test_migrating_twice_does_nothing_the_second_time() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        assert migrate(db, NOW) == ()


def test_the_second_migration_brings_the_later_tables() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        tables = db.tables()
        for name in (
            "technician",
            "certification",
            "competency",
            "location",
            "package",
            "duty_log",
        ):
            assert name in tables


def test_the_version_table_records_when_and_what() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        rows = db.query("SELECT version, applied_at, name FROM schema_version ORDER BY version")
        assert rows[0]["applied_at"] == "2024-11-01T09:00:00"
        assert rows[1]["name"] == "people, storage and the repair bench"
        assert rows[2]["name"] == "equipment carries its own capability"
        assert rows[3]["name"] == "tray events are numbered"


def test_a_migration_describes_itself() -> None:
    assert MIGRATIONS[0].describe() == "001 core records"


def test_a_partly_migrated_database_finishes_the_rest() -> None:
    with Database.in_memory() as db:
        db.script(MIGRATIONS[0].sql)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [1, NOW.isoformat(), "core records"],
        )
        done = migrate(db, NOW)
        assert [item.version for item in done] == [
            item.version for item in MIGRATIONS if item.version > 1
        ]


def test_a_clean_history_has_no_problems() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        assert problems(db) == ()
        ensure_current(db)


def test_a_database_behind_the_build_is_refused() -> None:
    with Database.in_memory() as db:
        db.script(MIGRATIONS[0].sql)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [1, NOW.isoformat(), "core records"],
        )
        with pytest.raises(ConflictError):
            ensure_current(db)


def test_a_version_from_a_newer_build_is_named() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [99, NOW.isoformat(), "from the future"],
        )
        assert problems(db) == ("version 99 was applied by a newer build",)
        with pytest.raises(IntegrityError):
            ensure_current(db)


def test_a_skipped_version_is_named() -> None:
    with Database.in_memory() as db:
        db.script(MIGRATIONS[0].sql)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [2, NOW.isoformat(), "second only"],
        )
        assert problems(db) == ("version 1 was skipped",)


def test_a_repeated_version_is_named() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [2, NOW.isoformat(), "again"],
        )
        assert "a migration is recorded twice" in problems(db)


def test_every_migration_has_a_distinct_version() -> None:
    versions = [migration.version for migration in MIGRATIONS]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


def _apply_through(db: Database, version: int) -> None:
    for migration in MIGRATIONS:
        if migration.version > version:
            break
        db.script(migration.sql)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [migration.version, NOW.isoformat(), migration.name],
        )


def test_existing_tray_events_are_numbered_in_order() -> None:
    with Database.in_memory() as db:
        _apply_through(db, 3)
        db.execute(
            "INSERT INTO tray (asset, code, ownership) VALUES (?, ?, ?)",
            ["ORT-0114", "ORT-MAJOR", "department"],
        )
        db.execute_many(
            "INSERT INTO tray_event (asset, at, stage, by_badge) VALUES (?, ?, ?, ?)",
            [
                ["ORT-0114", "2025-01-28T08:00:00", "soiled", "T-4471"],
                ["ORT-0114", "2025-01-28T09:00:00", "decontamination", "T-4471"],
                ["ORT-0114", "2025-01-28T10:00:00", "clean", "T-4471"],
            ],
        )
        migrate(db, NOW)
        rows = db.query(
            "SELECT seq, stage FROM tray_event WHERE asset = ? ORDER BY seq", ["ORT-0114"]
        )
        assert [row["seq"] for row in rows] == [1, 2, 3]
        assert [row["stage"] for row in rows] == ["soiled", "decontamination", "clean"]


def test_events_of_two_trays_are_numbered_separately() -> None:
    with Database.in_memory() as db:
        _apply_through(db, 3)
        for asset in ("ORT-0114", "ORT-0115"):
            db.execute(
                "INSERT INTO tray (asset, code, ownership) VALUES (?, ?, ?)",
                [asset, "ORT-MAJOR", "department"],
            )
            db.execute_many(
                "INSERT INTO tray_event (asset, at, stage, by_badge) VALUES (?, ?, ?, ?)",
                [
                    [asset, "2025-01-28T08:00:00", "soiled", "T-4471"],
                    [asset, "2025-01-28T09:00:00", "decontamination", "T-4471"],
                ],
            )
        migrate(db, NOW)
        rows = db.query("SELECT asset, seq FROM tray_event ORDER BY asset, seq")
        assert [(row["asset"], row["seq"]) for row in rows] == [
            ("ORT-0114", 1),
            ("ORT-0114", 2),
            ("ORT-0115", 1),
            ("ORT-0115", 2),
        ]


def test_the_numbering_migration_keeps_the_foreign_key() -> None:
    with Database.in_memory() as db:
        migrate(db, NOW)
        with pytest.raises(IntegrityError):
            db.execute(
                "INSERT INTO tray_event (asset, seq, at, stage, by_badge) VALUES (?, ?, ?, ?, ?)",
                ["MISSING", 1, "2025-01-28T08:00:00", "soiled", "T-4471"],
            )
