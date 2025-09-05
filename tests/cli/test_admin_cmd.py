from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from sterilot.cli.main import main
from sterilot.store.db import Database
from sterilot.store.migrations import MIGRATIONS, latest_version
from tests.cli.conftest import add_sterilizer, invoke, record_cycle


def test_opening_without_migrating_leaves_the_schema_alone(tmp_path: Path) -> None:
    path = str(tmp_path / "sterilot.sqlite3")
    Database.open(path).close()
    result = invoke(path, "status", migrate=False)
    assert result.exit_code == 0
    assert "schema" in result.output
    assert "0" in result.output


def test_migrate_says_it_is_already_current(db: str) -> None:
    invoke(db, "status")
    result = invoke(db, "admin", "migrate")
    assert result.exit_code == 0
    assert f"already at version {latest_version()}" in result.output


def test_a_dry_run_lists_what_would_apply(tmp_path: Path) -> None:
    path = str(tmp_path / "sterilot.sqlite3")
    Database.open(path).close()
    result = invoke(path, "admin", "migrate", "--dry-run", migrate=False)
    assert result.exit_code == 0
    assert MIGRATIONS[0].describe() in result.output


def test_the_table_list_counts_rows(db: str) -> None:
    add_sterilizer(db)
    result = invoke(db, "admin", "tables")
    assert result.exit_code == 0
    assert "equipment" in result.output
    assert "schema_version" in result.output


def test_a_backup_is_written(db: str, tmp_path: Path) -> None:
    add_sterilizer(db)
    target = tmp_path / "backup.sqlite3"
    result = invoke(db, "admin", "backup", str(target))
    assert result.exit_code == 0
    assert target.exists()
    assert "bytes" in result.output


def test_the_backup_holds_the_same_records(db: str, tmp_path: Path) -> None:
    add_sterilizer(db)
    target = tmp_path / "backup.sqlite3"
    invoke(db, "admin", "backup", str(target))
    result = invoke(str(target), "machine", "list")
    assert "AC-1" in result.output


def test_a_backup_will_not_overwrite_without_being_told(db: str, tmp_path: Path) -> None:
    target = tmp_path / "backup.sqlite3"
    invoke(db, "admin", "backup", str(target))
    again = invoke(db, "admin", "backup", str(target))
    assert again.exit_code == 4
    forced = invoke(db, "admin", "backup", str(target), "--overwrite")
    assert forced.exit_code == 0


def test_compacting_reports_the_page_count(db: str) -> None:
    add_sterilizer(db)
    result = invoke(db, "admin", "compact")
    assert result.exit_code == 0
    assert "pages before" in result.output


def test_the_settings_are_printed(db: str) -> None:
    result = invoke(db, "admin", "settings")
    assert "facility" in result.output
    assert "set_weight_limit_kg" in result.output


def test_a_clean_period_reports_clean(db: str) -> None:
    add_sterilizer(db)
    result = invoke(db, "admin", "compliance", "--from", "2025-04-01", "--to", "2025-04-08")
    assert result.exit_code == 0
    assert "clean" in result.output


def test_a_period_with_a_gap_exits_with_the_policy_status(db: str) -> None:
    add_sterilizer(db)
    record_cycle(db, "2025-04-02 08:00", run=1)
    result = invoke(db, "admin", "compliance", "--from", "2025-04-01", "--to", "2025-04-08")
    assert result.exit_code == 5
    assert "see below" in result.output
    assert "AC-1" in result.output


def test_migrating_an_old_file_brings_it_up(tmp_path: Path) -> None:
    path = str(tmp_path / "sterilot.sqlite3")
    db = Database.open(path)
    db.script(MIGRATIONS[0].sql)
    db.execute(
        "INSERT INTO schema_version (version, applied_at, name) VALUES (?, ?, ?)",
        [1, "2025-04-01T09:00:00", MIGRATIONS[0].name],
    )
    db.close()
    result = invoke(path, "admin", "migrate", migrate=False)
    assert result.exit_code == 0
    assert f"now at version {latest_version()}" in result.output


def test_a_purge_dry_run_removes_nothing(db: str) -> None:
    add_sterilizer(db)
    result = invoke(db, "admin", "purge", "--years", "7")
    assert result.exit_code == 0
    assert "nothing to remove" in result.output


def test_a_short_retention_is_refused(db: str) -> None:
    result = invoke(db, "admin", "purge", "--years", "1")
    assert result.exit_code == 2
    assert "retention floor" in result.output


def test_the_settings_can_be_written_out(db: str, tmp_path: Path) -> None:
    target = tmp_path / "sterilot.toml"
    result = invoke(db, "admin", "settings", "--write", str(target))
    assert result.exit_code == 0
    assert "wrote" in result.output
    assert "[sterilot]" in target.read_text(encoding="utf-8")


def test_the_written_settings_are_accepted_back(db: str, tmp_path: Path) -> None:
    target = tmp_path / "sterilot.toml"
    invoke(db, "admin", "settings", "--write", str(target))
    result = CliRunner().invoke(main, ["--db", db, "--settings", str(target), "admin", "settings"])
    assert result.exit_code == 0
    assert "Central Service" in result.output


def test_writing_will_not_overwrite_without_being_told(db: str, tmp_path: Path) -> None:
    target = tmp_path / "sterilot.toml"
    invoke(db, "admin", "settings", "--write", str(target))
    again = invoke(db, "admin", "settings", "--write", str(target))
    assert again.exit_code == 4
    forced = invoke(db, "admin", "settings", "--write", str(target), "--overwrite")
    assert forced.exit_code == 0
