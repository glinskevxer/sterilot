"""The database handle.

One SQLite file, because a central service department is one room with one
server under a desk and the backup story has to be "copy this file". The
pragmas below are not decoration:

Foreign keys are off by default in SQLite, which surprises everybody once. Write
ahead logging lets the assembly bench read while the sterilizer log writes.
A busy timeout stops a scanner at the far end of the room raising an exception
because somebody else was mid transaction.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sterilot.errors import ConflictError, IntegrityError, NotFoundError

BUSY_TIMEOUT_MS = 5000


@dataclass
class Database:
    """An open connection, with the department's pragmas applied."""

    connection: sqlite3.Connection
    path: str
    depth: int = 0
    """How many transactions are open. SQLite has no nested ones."""

    @classmethod
    def open(cls, path: Path | str) -> Database:
        target = str(path)
        connection = sqlite3.connect(target, isolation_level=None)
        return cls._prepared(connection, target)

    @classmethod
    def in_memory(cls) -> Database:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        return cls._prepared(connection, ":memory:")

    @classmethod
    def _prepared(cls, connection: sqlite3.Connection, path: str) -> Database:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA synchronous = NORMAL")
        if path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return cls(connection, path)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def execute(self, sql: str, parameters: Sequence[Any] | None = None) -> sqlite3.Cursor:
        try:
            return self.connection.execute(sql, tuple(parameters or ()))
        except sqlite3.IntegrityError as exc:
            raise _integrity(exc, sql) from exc

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        try:
            self.connection.executemany(sql, [tuple(row) for row in rows])
        except sqlite3.IntegrityError as exc:
            raise _integrity(exc, sql) from exc

    def script(self, sql: str) -> None:
        self.connection.executescript(sql)

    def query(self, sql: str, parameters: Sequence[Any] | None = None) -> list[sqlite3.Row]:
        return list(self.execute(sql, parameters).fetchall())

    def query_one(self, sql: str, parameters: Sequence[Any] | None = None) -> sqlite3.Row | None:
        rows = self.execute(sql, parameters).fetchmany(2)
        if len(rows) > 1:
            raise IntegrityError("that query was expected to match one row", sql=sql)
        return rows[0] if rows else None

    def require_one(self, sql: str, parameters: Sequence[Any] | None = None) -> sqlite3.Row:
        row = self.query_one(sql, parameters)
        if row is None:
            raise NotFoundError("nothing matched", sql=sql)
        return row

    def scalar(self, sql: str, parameters: Sequence[Any] | None = None) -> Any:
        row = self.query_one(sql, parameters)
        return None if row is None else row[0]

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """Everything inside lands together or not at all.

        Reentrant, because one repository write legitimately calls another and
        neither should have to know whether it is the outer one. Only the
        outermost block starts and finishes the transaction, so a failure
        anywhere inside rolls the whole thing back.
        """
        if self.depth:
            self.depth += 1
            try:
                yield self
            finally:
                self.depth -= 1
            return
        self.connection.execute("BEGIN")
        self.depth = 1
        try:
            yield self
        except BaseException:
            self.depth = 0
            self.connection.execute("ROLLBACK")
            raise
        self.depth = 0
        self.connection.execute("COMMIT")

    def checkpoint(self) -> tuple[int, int]:
        """Fold the write ahead log back into the database file.

        Returns the pages written and the pages left. Outside write ahead mode
        SQLite answers with minus one for both, which is not a page count, so
        it comes back as zero: nothing was written and nothing is left.
        """
        row = self.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if row is None:
            return 0, 0
        return max(int(row[1] or 0), 0), max(int(row[2] or 0), 0)

    def journal_mode(self) -> str:
        found = self.scalar("PRAGMA journal_mode")
        return str(found)

    def in_use(self) -> bool:
        """True while this connection is inside a transaction."""
        return bool(self.connection.in_transaction)

    def tables(self) -> tuple[str, ...]:
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        )
        return tuple(str(row["name"]) for row in rows)

    def integrity_problems(self) -> tuple[str, ...]:
        """SQLite's own checks, plus the foreign keys it does not check on its own."""
        found: list[str] = []
        for row in self.query("PRAGMA integrity_check"):
            message = str(row[0])
            if message != "ok":
                found.append(message)
        for row in self.query("PRAGMA foreign_key_check"):
            found.append(f"{row[0]} row {row[1]} breaks a reference to {row[2]}")
        return tuple(found)


def _integrity(exc: sqlite3.IntegrityError, sql: str) -> Exception:
    message = str(exc)
    if "UNIQUE" in message:
        return ConflictError("that record already exists", detail=message)
    return IntegrityError("the write broke a constraint", detail=message, sql=sql.strip()[:60])
