from __future__ import annotations

import pytest

from sterilot.errors import ConflictError, IntegrityError
from sterilot.store.db import Database
from sterilot.store.schema import applied_versions, create_all, is_empty


def prepared() -> Database:
    db = Database.in_memory()
    create_all(db)
    return db


def test_an_untouched_database_is_empty() -> None:
    with Database.in_memory() as db:
        assert is_empty(db)
        assert applied_versions(db) == ()


def test_creating_the_schema_makes_every_table() -> None:
    with prepared() as db:
        tables = db.tables()
        for name in (
            "instrument",
            "sheet",
            "sheet_line",
            "substitution",
            "tray",
            "tray_event",
            "equipment",
            "sterilizer_cycle",
            "washer_cycle",
            "washer_phase",
            "load_record",
            "load_item",
            "issue",
            "nonconformance",
            "audit_event",
            "schema_version",
        ):
            assert name in tables


def test_creating_twice_is_harmless() -> None:
    with prepared() as db:
        create_all(db)
        assert not is_empty(db)


def test_a_sheet_line_needs_an_instrument_that_exists() -> None:
    with prepared() as db:
        db.execute(
            "INSERT INTO sheet (code, revision, name, starts_on) VALUES (?, ?, ?, ?)",
            ["ORT-MAJOR", 1, "ortho major", "2024-01-01"],
        )
        with pytest.raises(IntegrityError):
            db.execute(
                "INSERT INTO sheet_line (code, revision, catalog, quantity) VALUES (?, ?, ?, ?)",
                ["ORT-MAJOR", 1, "SU-9999", 2],
            )


def test_a_sheet_line_needs_a_sheet_that_exists() -> None:
    with prepared() as db:
        db.execute(
            "INSERT INTO instrument (catalog, description, manufacturer, material, complexity,"
            " criticality) VALUES (?, ?, ?, ?, ?, ?)",
            ["SU-1234", "forceps", "V Mueller", "SS", "hinged", "critical"],
        )
        with pytest.raises(IntegrityError):
            db.execute(
                "INSERT INTO sheet_line (code, revision, catalog, quantity) VALUES (?, ?, ?, ?)",
                ["GEN-MINOR", 1, "SU-1234", 2],
            )


def test_a_tray_cannot_be_registered_twice() -> None:
    with prepared() as db:
        db.execute(
            "INSERT INTO tray (asset, code, ownership) VALUES (?, ?, ?)",
            ["ORT-0114", "ORT-MAJOR", "department"],
        )
        with pytest.raises(ConflictError):
            db.execute(
                "INSERT INTO tray (asset, code, ownership) VALUES (?, ?, ?)",
                ["ORT-0114", "ORT-MAJOR", "department"],
            )


def test_a_load_needs_a_cycle_to_hang_from() -> None:
    with prepared() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                "INSERT INTO load_record (reference, lot, method, built_by, built_at, status)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    "LD-1",
                    "AC-1-20241030-01",
                    "steam_prevac",
                    "T-4471",
                    "2024-10-30T08:00",
                    "pending",
                ],
            )


def test_a_washer_phase_needs_its_cycle() -> None:
    with prepared() as db:
        db.execute(
            "INSERT INTO equipment (equipment_id, kind, model, manufacturer) VALUES (?, ?, ?, ?)",
            ["WD-2", "washer", "Reliance", "Steris"],
        )
        with pytest.raises(IntegrityError):
            db.execute(
                "INSERT INTO washer_phase (equipment_id, started_at, number, phase, seconds)"
                " VALUES (?, ?, ?, ?, ?)",
                ["WD-2", "2024-10-30T06:40", 318, "wash", 360.0],
            )


def test_the_audit_table_hands_out_its_own_sequence() -> None:
    with prepared() as db:
        for index in range(3):
            db.execute(
                "INSERT INTO audit_event (at, by_badge, action, subject_kind, subject, previous)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [f"2024-10-30T09:0{index}", "T-4471", "recorded", "load", "LD-1", "0" * 64],
            )
        rows = db.query("SELECT sequence FROM audit_event ORDER BY sequence")
        assert [row["sequence"] for row in rows] == [1, 2, 3]


def test_the_indexes_are_created() -> None:
    with prepared() as db:
        rows = db.query(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
        names = {str(row["name"]) for row in rows}
        assert "load_item_by_asset" in names
        assert "sterilizer_cycle_by_day" in names
