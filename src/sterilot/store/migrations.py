"""Schema migrations, applied in order and recorded.

The department's database lives on a machine under a desk and gets upgraded by
somebody running a command between cases. So migrations are numbered, they run
in order, each one lands inside a transaction, and the version table says what
has already happened. Running the command twice does nothing the second time.

There is no down migration. Rolling a hospital record system backwards loses
records, and the recovery for a bad upgrade is the backup taken before it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sterilot.errors import ConflictError, IntegrityError
from sterilot.store.db import Database
from sterilot.store.schema import SCHEMA_SQL

VERSION_TWO_SQL = """
CREATE TABLE IF NOT EXISTS technician (
  badge       TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  role        TEXT NOT NULL,
  starts_on   TEXT,
  ends_on     TEXT
);

CREATE TABLE IF NOT EXISTS certification (
  badge       TEXT NOT NULL REFERENCES technician(badge),
  body        TEXT NOT NULL,
  number      TEXT NOT NULL,
  starts_on   TEXT NOT NULL,
  ends_on     TEXT,
  PRIMARY KEY (badge, body, number)
);

CREATE TABLE IF NOT EXISTS competency (
  badge        TEXT NOT NULL REFERENCES technician(badge),
  task         TEXT NOT NULL,
  assessed_on  TEXT NOT NULL,
  assessor     TEXT NOT NULL,
  observations INTEGER NOT NULL DEFAULT 1,
  valid_until  TEXT,
  PRIMARY KEY (badge, task, assessed_on)
);

CREATE TABLE IF NOT EXISTS location (
  code            TEXT PRIMARY KEY,
  description     TEXT NOT NULL,
  zone            TEXT NOT NULL,
  capacity_units  INTEGER NOT NULL,
  floor_cm        REAL NOT NULL,
  sprinkler_cm    REAL NOT NULL,
  wall_cm         REAL NOT NULL DEFAULT 10,
  closed_shelving INTEGER NOT NULL DEFAULT 1,
  under_plumbing  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS par_level (
  code     TEXT PRIMARY KEY,
  minimum  INTEGER NOT NULL,
  target   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS package (
  asset          TEXT NOT NULL,
  lot            TEXT NOT NULL,
  packaging      TEXT NOT NULL,
  sterilized_at  TEXT NOT NULL,
  location       TEXT REFERENCES location(code),
  PRIMARY KEY (asset, lot)
);

CREATE TABLE IF NOT EXISTS package_event (
  asset   TEXT NOT NULL,
  lot     TEXT NOT NULL,
  at      TEXT NOT NULL,
  event   TEXT NOT NULL,
  by_badge TEXT NOT NULL,
  note    TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (asset, lot, at, event),
  FOREIGN KEY (asset, lot) REFERENCES package(asset, lot)
);

CREATE TABLE IF NOT EXISTS duty_log (
  day          TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  duty         TEXT NOT NULL,
  passed       INTEGER NOT NULL,
  by_badge     TEXT NOT NULL,
  note         TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (day, equipment_id, duty)
);

CREATE TABLE IF NOT EXISTS repair_order (
  reference   TEXT PRIMARY KEY,
  asset       TEXT NOT NULL,
  catalog     TEXT NOT NULL,
  out_of_code TEXT NOT NULL,
  vendor      TEXT NOT NULL,
  fault       TEXT NOT NULL,
  raised_at   TEXT NOT NULL,
  raised_by   TEXT NOT NULL,
  status      TEXT NOT NULL,
  quote_cents INTEGER,
  approved_by TEXT NOT NULL DEFAULT '',
  sent_at     TEXT,
  closed_at   TEXT
);

CREATE INDEX IF NOT EXISTS repair_by_set ON repair_order (out_of_code, status);
"""


VERSION_THREE_SQL = """
ALTER TABLE equipment ADD COLUMN methods TEXT NOT NULL DEFAULT '';
ALTER TABLE equipment ADD COLUMN chamber TEXT;
ALTER TABLE equipment ADD COLUMN chambers INTEGER NOT NULL DEFAULT 1;
ALTER TABLE equipment ADD COLUMN installed_on TEXT;
ALTER TABLE equipment ADD COLUMN retired_on TEXT;
ALTER TABLE equipment ADD COLUMN out_of_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE equipment ADD COLUMN qualification_owed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE equipment ADD COLUMN last_qualification TEXT;
"""


VERSION_FOUR_SQL = """
CREATE TABLE tray_event_numbered (
  asset     TEXT    NOT NULL REFERENCES tray(asset),
  seq       INTEGER NOT NULL,
  at        TEXT    NOT NULL,
  stage     TEXT    NOT NULL,
  by_badge  TEXT    NOT NULL,
  note      TEXT    NOT NULL DEFAULT '',
  PRIMARY KEY (asset, seq)
);

INSERT INTO tray_event_numbered (asset, seq, at, stage, by_badge, note)
SELECT asset,
       row_number() OVER (PARTITION BY asset ORDER BY at, rowid),
       at, stage, by_badge, note
FROM tray_event;

DROP TABLE tray_event;
ALTER TABLE tray_event_numbered RENAME TO tray_event;
"""


VERSION_FIVE_SQL = """
CREATE TABLE IF NOT EXISTS wash_program (
  name          TEXT PRIMARY KEY,
  washer_class  TEXT NOT NULL,
  a0_floor      REAL
);

CREATE TABLE IF NOT EXISTS wash_program_phase (
  name        TEXT NOT NULL REFERENCES wash_program(name),
  phase       TEXT NOT NULL,
  minimum_s   REAL NOT NULL,
  low_c       REAL,
  high_c      REAL,
  detergent   TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (name, phase)
);
"""


VERSION_SIX_SQL = """
CREATE TABLE IF NOT EXISTS loaner (
  reference        TEXT PRIMARY KEY,
  vendor           TEXT NOT NULL,
  set_name         TEXT NOT NULL,
  case_number      TEXT NOT NULL,
  case_start       TEXT NOT NULL,
  expected_at      TEXT NOT NULL,
  received_at      TEXT,
  counted_at       TEXT,
  reprocessed_at   TEXT,
  released_at      TEXT,
  decontaminated_at TEXT,
  returned_at      TEXT,
  piece_count      INTEGER,
  rep_present      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS loaner_by_case ON loaner (case_number);
"""


VERSION_SEVEN_SQL = """
CREATE TABLE IF NOT EXISTS verification (
  equipment_id  TEXT    NOT NULL,
  at            TEXT    NOT NULL,
  kind          TEXT    NOT NULL,
  value         REAL,
  visual_pass   INTEGER,
  by_badge      TEXT    NOT NULL,
  lot           TEXT    NOT NULL DEFAULT '',
  subject       TEXT    NOT NULL DEFAULT '',
  PRIMARY KEY (equipment_id, at, kind, subject)
);

CREATE INDEX IF NOT EXISTS verification_by_day ON verification (equipment_id, at);
"""


VERSION_EIGHT_SQL = """
CREATE TABLE IF NOT EXISTS scheduled_case (
  case_number  TEXT PRIMARY KEY,
  room         TEXT NOT NULL,
  surgeon      TEXT NOT NULL,
  procedure    TEXT NOT NULL,
  starts_at    TEXT NOT NULL,
  minutes      INTEGER NOT NULL,
  card_ref     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS case_by_start ON scheduled_case (starts_at);

CREATE TABLE IF NOT EXISTS preference_card (
  reference   TEXT NOT NULL,
  revision    INTEGER NOT NULL,
  surgeon     TEXT NOT NULL,
  procedure   TEXT NOT NULL,
  starts_on   TEXT NOT NULL,
  ends_on     TEXT,
  loaner_sets TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (reference, revision)
);

CREATE TABLE IF NOT EXISTS preference_card_line (
  reference  TEXT NOT NULL,
  revision   INTEGER NOT NULL,
  code       TEXT NOT NULL,
  quantity   INTEGER NOT NULL,
  essential  INTEGER NOT NULL DEFAULT 1,
  note       TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (reference, revision, code),
  FOREIGN KEY (reference, revision) REFERENCES preference_card(reference, revision)
);
"""


VERSION_NINE_SQL = """
CREATE TABLE IF NOT EXISTS case_cart (
  reference     TEXT PRIMARY KEY,
  case_number   TEXT NOT NULL,
  card_ref      TEXT NOT NULL,
  built_by      TEXT NOT NULL,
  built_at      TEXT NOT NULL,
  delivered_at  TEXT
);

CREATE INDEX IF NOT EXISTS cart_by_case ON case_cart (case_number);

CREATE TABLE IF NOT EXISTS case_cart_line (
  reference  TEXT NOT NULL REFERENCES case_cart(reference),
  asset      TEXT NOT NULL,
  code       TEXT NOT NULL,
  location   TEXT NOT NULL DEFAULT '',
  picked_by  TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (reference, asset)
);
"""


VERSION_TEN_SQL = """
CREATE TABLE IF NOT EXISTS container (
  asset            TEXT PRIMARY KEY,
  model            TEXT NOT NULL,
  manufacturer     TEXT NOT NULL,
  filter_type      TEXT NOT NULL,
  filter_positions INTEGER NOT NULL DEFAULT 2,
  starts_on        TEXT,
  ends_on          TEXT,
  last_inspection  TEXT,
  cycles_since     INTEGER NOT NULL DEFAULT 0,
  gasket_intact    INTEGER NOT NULL DEFAULT 1,
  latches_intact   INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass(frozen=True)
class Migration:
    """One numbered step."""

    version: int
    name: str
    sql: str

    def describe(self) -> str:
        return f"{self.version:03d} {self.name}"


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "core records", SCHEMA_SQL),
    Migration(2, "people, storage and the repair bench", VERSION_TWO_SQL),
    Migration(3, "equipment carries its own capability", VERSION_THREE_SQL),
    Migration(4, "tray events are numbered", VERSION_FOUR_SQL),
    Migration(5, "wash programs live in the database", VERSION_FIVE_SQL),
    Migration(6, "vendor loaners", VERSION_SIX_SQL),
    Migration(7, "cleaning verification results", VERSION_SEVEN_SQL),
    Migration(8, "the theatre list and preference cards", VERSION_EIGHT_SQL),
    Migration(9, "case carts", VERSION_NINE_SQL),
    Migration(10, "rigid containers", VERSION_TEN_SQL),
)


def latest_version() -> int:
    return max(migration.version for migration in MIGRATIONS)


def current_version(db: Database) -> int:
    """The highest version applied, or zero on a fresh database."""
    if "schema_version" not in db.tables():
        return 0
    found = db.scalar("SELECT max(version) FROM schema_version")
    return int(found) if found is not None else 0


def applied(db: Database) -> tuple[int, ...]:
    if "schema_version" not in db.tables():
        return ()
    rows = db.query("SELECT version FROM schema_version ORDER BY version")
    return tuple(int(row["version"]) for row in rows)


def pending(db: Database) -> tuple[Migration, ...]:
    done = set(applied(db))
    return tuple(migration for migration in MIGRATIONS if migration.version not in done)


def migrate(db: Database, now: datetime | None = None) -> tuple[Migration, ...]:
    """Apply everything outstanding, in order, and record each one."""
    stamp = (now or datetime.now()).replace(microsecond=0)
    done: list[Migration] = []
    for migration in pending(db):
        db.script(migration.sql)
        db.execute(
            "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
            [migration.version, stamp.isoformat(timespec="seconds"), migration.name],
        )
        done.append(migration)
    return tuple(done)


def problems(db: Database) -> tuple[str, ...]:
    """Anything odd about what has been applied."""
    found: list[str] = []
    known = {migration.version for migration in MIGRATIONS}
    recorded = applied(db)
    if len(set(recorded)) != len(recorded):
        found.append("a migration is recorded twice")
    for version in recorded:
        if version not in known:
            found.append(f"version {version} was applied by a newer build")
    highest = max(recorded) if recorded else 0
    for version in sorted(known):
        if version < highest and version not in recorded:
            found.append(f"version {version} was skipped")
    return tuple(found)


def ensure_current(db: Database) -> None:
    """Refuse to work against a database that is behind or ahead."""
    trouble = problems(db)
    if trouble:
        raise IntegrityError("the schema history does not add up", detail="; ".join(trouble))
    if current_version(db) != latest_version():
        raise ConflictError(
            "the database needs migrating",
            current=current_version(db),
            latest=latest_version(),
        )
