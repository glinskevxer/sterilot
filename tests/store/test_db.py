from __future__ import annotations

from pathlib import Path

import pytest

from sterilot.errors import ConflictError, IntegrityError, NotFoundError
from sterilot.store.db import Database

SETUP = """
CREATE TABLE parent (id TEXT PRIMARY KEY);
CREATE TABLE child (
  id TEXT PRIMARY KEY,
  parent_id TEXT NOT NULL REFERENCES parent(id)
);
"""


def prepared() -> Database:
    db = Database.in_memory()
    db.script(SETUP)
    return db


def test_a_memory_database_opens_with_foreign_keys_on() -> None:
    with prepared() as db:
        assert db.scalar("PRAGMA foreign_keys") == 1
        assert db.path == ":memory:"


def test_a_file_database_uses_write_ahead_logging(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.sqlite3"
    with Database.open(path) as db:
        assert db.scalar("PRAGMA journal_mode") == "wal"
    assert path.exists()


def test_tables_are_listed_in_order() -> None:
    with prepared() as db:
        assert db.tables() == ("child", "parent")


def test_rows_come_back_by_name() -> None:
    with prepared() as db:
        db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
        row = db.require_one("SELECT id FROM parent WHERE id = ?", ["P1"])
        assert row["id"] == "P1"


def test_query_one_returns_nothing_when_nothing_matches() -> None:
    with prepared() as db:
        assert db.query_one("SELECT id FROM parent WHERE id = ?", ["missing"]) is None


def test_query_one_refuses_two_rows() -> None:
    with prepared() as db:
        db.execute_many("INSERT INTO parent (id) VALUES (?)", [["P1"], ["P2"]])
        with pytest.raises(IntegrityError):
            db.query_one("SELECT id FROM parent")


def test_require_one_refuses_nothing() -> None:
    with prepared() as db:
        with pytest.raises(NotFoundError):
            db.require_one("SELECT id FROM parent WHERE id = ?", ["missing"])


def test_scalar_reads_the_first_column() -> None:
    with prepared() as db:
        assert db.scalar("SELECT count(*) FROM parent") == 0
        assert db.scalar("SELECT id FROM parent WHERE id = 'nope'") is None


def test_a_duplicate_key_reads_as_a_conflict() -> None:
    with prepared() as db:
        db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
        with pytest.raises(ConflictError):
            db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])


def test_a_broken_reference_reads_as_an_integrity_error() -> None:
    with prepared() as db:
        with pytest.raises(IntegrityError):
            db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "missing"])


def test_execute_many_reports_its_own_conflicts() -> None:
    with prepared() as db:
        with pytest.raises(ConflictError):
            db.execute_many("INSERT INTO parent (id) VALUES (?)", [["P1"], ["P1"]])


def test_a_transaction_commits_together() -> None:
    with prepared() as db:
        with db.transaction():
            db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
            db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "P1"])
        assert db.scalar("SELECT count(*) FROM child") == 1


def test_a_failed_transaction_leaves_nothing_behind() -> None:
    with prepared() as db:
        with pytest.raises(IntegrityError):
            with db.transaction():
                db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
                db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "missing"])
        assert db.scalar("SELECT count(*) FROM parent") == 0


def test_a_clean_database_reports_no_integrity_problems() -> None:
    with prepared() as db:
        db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
        db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "P1"])
        assert db.integrity_problems() == ()


def test_a_dangling_reference_is_found_when_the_keys_are_off() -> None:
    with prepared() as db:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "missing"])
        problems = db.integrity_problems()
        assert len(problems) == 1
        assert "breaks a reference to parent" in problems[0]


def test_a_nested_transaction_joins_the_outer_one() -> None:
    with prepared() as db:
        with db.transaction():
            db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
            with db.transaction():
                db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "P1"])
            assert db.depth == 1
        assert db.depth == 0
        assert db.scalar("SELECT count(*) FROM child") == 1


def test_a_failure_inside_a_nested_block_rolls_the_whole_thing_back() -> None:
    with prepared() as db:
        with pytest.raises(IntegrityError):
            with db.transaction():
                db.execute("INSERT INTO parent (id) VALUES (?)", ["P1"])
                with db.transaction():
                    db.execute("INSERT INTO child (id, parent_id) VALUES (?, ?)", ["C1", "missing"])
        assert db.depth == 0
        assert db.scalar("SELECT count(*) FROM parent") == 0


def test_the_depth_returns_to_zero_after_a_clean_run() -> None:
    with prepared() as db:
        with db.transaction():
            assert db.depth == 1
        assert db.depth == 0
        with db.transaction():
            db.execute("INSERT INTO parent (id) VALUES (?)", ["P2"])
        assert db.scalar("SELECT count(*) FROM parent") == 1
