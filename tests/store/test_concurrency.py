"""Two connections to one file, which is what the department actually has.

The assembly bench, the sterilizer log and whoever is running a report are
three processes on one database. SQLite handles that as long as the write ahead
log is on and everybody waits their turn, and these tests hold that behaviour
down rather than assuming it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sterilot.errors import ConflictError
from sterilot.store.db import BUSY_TIMEOUT_MS, Database
from sterilot.store.store import Store


def test_a_file_database_runs_in_write_ahead_mode(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Database.open(path) as db:
        assert db.journal_mode() == "wal"


def test_an_in_memory_database_has_no_write_ahead_log() -> None:
    with Database.in_memory() as db:
        assert db.journal_mode() == "memory"
        assert db.checkpoint() == (0, 0)


def test_a_checkpoint_folds_the_log_back(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as store:
        store.db.execute(
            "INSERT INTO equipment (equipment_id, kind, model, manufacturer) VALUES (?, ?, ?, ?)",
            ["AC-1", "sterilizer", "Amsco", "Steris"],
        )
        written, left = store.db.checkpoint()
        assert written >= 0
        assert left == 0


def test_a_second_connection_sees_a_committed_write(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as first:
        first.db.execute(
            "INSERT INTO equipment (equipment_id, kind, model, manufacturer) VALUES (?, ?, ?, ?)",
            ["AC-1", "sterilizer", "Amsco", "Steris"],
        )
        with Store.open(path) as second:
            assert second.equipment.exists("AC-1")


def test_a_reader_does_not_see_an_uncommitted_write(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as writer, Store.open(path) as reader:
        with writer.db.transaction():
            writer.db.execute(
                "INSERT INTO equipment (equipment_id, kind, model, manufacturer)"
                " VALUES (?, ?, ?, ?)",
                ["AC-2", "sterilizer", "Amsco", "Steris"],
            )
            assert writer.db.in_use()
            assert not reader.equipment.exists("AC-2")
        assert reader.equipment.exists("AC-2")


def test_a_rolled_back_write_is_never_seen(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as writer, Store.open(path) as reader:
        with pytest.raises(ConflictError):
            with writer.db.transaction():
                writer.db.execute(
                    "INSERT INTO equipment (equipment_id, kind, model, manufacturer)"
                    " VALUES (?, ?, ?, ?)",
                    ["AC-3", "sterilizer", "Amsco", "Steris"],
                )
                writer.db.execute(
                    "INSERT INTO equipment (equipment_id, kind, model, manufacturer)"
                    " VALUES (?, ?, ?, ?)",
                    ["AC-3", "sterilizer", "Amsco", "Steris"],
                )
        assert not reader.equipment.exists("AC-3")
        assert not writer.db.in_use()


def test_two_writers_do_not_both_get_the_same_key(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as first, Store.open(path) as second:
        first.db.execute(
            "INSERT INTO equipment (equipment_id, kind, model, manufacturer) VALUES (?, ?, ?, ?)",
            ["AC-4", "sterilizer", "Amsco", "Steris"],
        )
        with pytest.raises(ConflictError):
            second.db.execute(
                "INSERT INTO equipment (equipment_id, kind, model, manufacturer)"
                " VALUES (?, ?, ?, ?)",
                ["AC-4", "sterilizer", "Amsco", "Steris"],
            )


def test_the_busy_timeout_is_set_on_every_connection(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Database.open(path) as db:
        assert db.scalar("PRAGMA busy_timeout") == BUSY_TIMEOUT_MS


def test_a_writer_holding_the_lock_blocks_another_writer(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Store.open(path) as holder:
        holder.db.execute("PRAGMA busy_timeout = 50")
        second = Database.open(path)
        second.execute("PRAGMA busy_timeout = 50")
        try:
            with holder.db.transaction():
                holder.db.execute(
                    "INSERT INTO equipment (equipment_id, kind, model, manufacturer)"
                    " VALUES (?, ?, ?, ?)",
                    ["AC-5", "sterilizer", "Amsco", "Steris"],
                )
                with pytest.raises(sqlite3.OperationalError):
                    second.execute("BEGIN EXCLUSIVE")
        finally:
            second.close()
