"""The tables, written out once.

A few decisions worth stating rather than leaving to be inferred:

Identifiers are the department's own codes, not surrogate integers. A tray is
ORT-0114 on the shelf, on the label and in the database, and an audit that has
to join through a number nobody can see is an audit nobody finishes.

Everything that can be dated is dated as ISO text. SQLite has no date type and
ISO text sorts correctly, which is the only property the queries need.

Deletes are not cascaded anywhere. A load whose cycle somebody wants to remove
is a conversation, not a foreign key action.
"""

from __future__ import annotations

from sterilot.store.db import Database

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER NOT NULL,
  applied_at  TEXT    NOT NULL,
  name        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS instrument (
  catalog       TEXT PRIMARY KEY,
  description   TEXT NOT NULL,
  manufacturer  TEXT NOT NULL,
  material      TEXT NOT NULL,
  complexity    TEXT NOT NULL,
  criticality   TEXT NOT NULL,
  lumen_mm      REAL,
  lumen_len_mm  REAL,
  disassembly   INTEGER NOT NULL DEFAULT 0,
  insulated     INTEGER NOT NULL DEFAULT 0,
  weight_g      REAL
);

CREATE TABLE IF NOT EXISTS sheet (
  code        TEXT NOT NULL,
  revision    INTEGER NOT NULL,
  name        TEXT NOT NULL,
  container   TEXT,
  starts_on   TEXT NOT NULL,
  ends_on     TEXT,
  note        TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (code, revision)
);

CREATE TABLE IF NOT EXISTS sheet_line (
  code        TEXT NOT NULL,
  revision    INTEGER NOT NULL,
  catalog     TEXT NOT NULL REFERENCES instrument(catalog),
  quantity    INTEGER NOT NULL,
  position    TEXT NOT NULL DEFAULT '',
  required    INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (code, revision, catalog),
  FOREIGN KEY (code, revision) REFERENCES sheet(code, revision)
);

CREATE TABLE IF NOT EXISTS substitution (
  original     TEXT NOT NULL REFERENCES instrument(catalog),
  replacement  TEXT NOT NULL REFERENCES instrument(catalog),
  starts_on    TEXT NOT NULL,
  ends_on      TEXT,
  ratio        INTEGER NOT NULL DEFAULT 1,
  approved_by  TEXT NOT NULL,
  reason       TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (original, replacement, starts_on)
);

CREATE TABLE IF NOT EXISTS tray (
  asset       TEXT PRIMARY KEY,
  code        TEXT NOT NULL,
  ownership   TEXT NOT NULL,
  owner       TEXT NOT NULL DEFAULT '',
  retired_on  TEXT
);

CREATE TABLE IF NOT EXISTS tray_event (
  asset     TEXT NOT NULL REFERENCES tray(asset),
  at        TEXT NOT NULL,
  stage     TEXT NOT NULL,
  by_badge  TEXT NOT NULL,
  note      TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (asset, at, stage)
);

CREATE TABLE IF NOT EXISTS equipment (
  equipment_id  TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  model         TEXT NOT NULL,
  manufacturer  TEXT NOT NULL,
  detail        TEXT NOT NULL DEFAULT '',
  in_service    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sterilizer_cycle (
  lot           TEXT PRIMARY KEY,
  equipment_id  TEXT NOT NULL REFERENCES equipment(equipment_id),
  run_date      TEXT NOT NULL,
  run           INTEGER NOT NULL,
  cycle_name    TEXT NOT NULL,
  method        TEXT NOT NULL,
  started_at    TEXT NOT NULL,
  operator      TEXT NOT NULL,
  hold_c        REAL NOT NULL,
  exposure_s    REAL NOT NULL,
  dry_s         REAL NOT NULL DEFAULT 0,
  pressure_kpa  REAL,
  pulses        INTEGER,
  aborted       INTEGER NOT NULL DEFAULT 0,
  abort_reason  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS sterilizer_cycle_by_day
  ON sterilizer_cycle (equipment_id, run_date, run);

CREATE TABLE IF NOT EXISTS washer_cycle (
  equipment_id  TEXT NOT NULL REFERENCES equipment(equipment_id),
  number        INTEGER NOT NULL,
  started_at    TEXT NOT NULL,
  program       TEXT NOT NULL,
  operator      TEXT NOT NULL,
  aborted       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (equipment_id, started_at, number)
);

CREATE TABLE IF NOT EXISTS washer_phase (
  equipment_id  TEXT NOT NULL,
  started_at    TEXT NOT NULL,
  number        INTEGER NOT NULL,
  phase         TEXT NOT NULL,
  seconds       REAL NOT NULL,
  peak_c        REAL,
  PRIMARY KEY (equipment_id, started_at, number, phase),
  FOREIGN KEY (equipment_id, started_at, number)
    REFERENCES washer_cycle(equipment_id, started_at, number)
);

CREATE TABLE IF NOT EXISTS load_record (
  reference   TEXT PRIMARY KEY,
  lot         TEXT NOT NULL REFERENCES sterilizer_cycle(lot),
  method      TEXT NOT NULL,
  built_by    TEXT NOT NULL,
  built_at    TEXT NOT NULL,
  status      TEXT NOT NULL,
  decided_at  TEXT,
  decided_by  TEXT,
  kind        TEXT,
  reasons     TEXT NOT NULL DEFAULT '',
  recalled_at TEXT,
  recall_note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS load_record_by_lot ON load_record (lot);

CREATE TABLE IF NOT EXISTS load_item (
  reference  TEXT NOT NULL REFERENCES load_record(reference),
  asset      TEXT NOT NULL,
  code       TEXT NOT NULL,
  units      INTEGER NOT NULL DEFAULT 1,
  weight_g   REAL,
  implant    INTEGER NOT NULL DEFAULT 0,
  textile    INTEGER NOT NULL DEFAULT 0,
  shelf      INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (reference, asset)
);

CREATE INDEX IF NOT EXISTS load_item_by_asset ON load_item (asset);

CREATE TABLE IF NOT EXISTS issue (
  asset        TEXT NOT NULL,
  issued_at    TEXT NOT NULL,
  case_number  TEXT NOT NULL,
  issued_by    TEXT NOT NULL,
  returned_at  TEXT,
  disposition  TEXT NOT NULL,
  PRIMARY KEY (asset, issued_at)
);

CREATE INDEX IF NOT EXISTS issue_by_case ON issue (case_number);

CREATE TABLE IF NOT EXISTS nonconformance (
  reference    TEXT PRIMARY KEY,
  category     TEXT NOT NULL,
  severity     TEXT NOT NULL,
  raised_at    TEXT NOT NULL,
  raised_by    TEXT NOT NULL,
  description  TEXT NOT NULL,
  subject      TEXT NOT NULL DEFAULT '',
  action       TEXT NOT NULL DEFAULT '',
  investigation TEXT NOT NULL DEFAULT '',
  closed_at    TEXT,
  closed_by    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_event (
  sequence      INTEGER PRIMARY KEY AUTOINCREMENT,
  at            TEXT NOT NULL,
  by_badge      TEXT NOT NULL,
  action        TEXT NOT NULL,
  subject_kind  TEXT NOT NULL,
  subject       TEXT NOT NULL,
  detail        TEXT NOT NULL DEFAULT '',
  previous      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_by_subject ON audit_event (subject_kind, subject);
"""


def create_all(db: Database) -> None:
    """Create every table. Safe to run against a database that has them."""
    db.script(SCHEMA_SQL)


def is_empty(db: Database) -> bool:
    return not db.tables()


def applied_versions(db: Database) -> tuple[int, ...]:
    if "schema_version" not in db.tables():
        return ()
    rows = db.query("SELECT version FROM schema_version ORDER BY version")
    return tuple(int(row["version"]) for row in rows)
