"""Administrative commands.

Migrating, backing up, compacting and exporting. The backup is a real one: it
uses SQLite's own backup so a copy taken while somebody is scanning a tray is
still a consistent database, which a file copy is not.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.errors import ConflictError
from sterilot.reporting import compliance
from sterilot.reporting.render import Column, bullets, pairs, table
from sterilot.store import retention
from sterilot.store.migrations import current_version, latest_version, migrate, pending


@click.group()
def admin() -> None:
    """Looking after the database."""


@admin.command("migrate")
@click.option("--dry-run", is_flag=True, help="say what would run without running it")
@click.pass_obj
def migrate_command(context: Context, dry_run: bool) -> None:
    """Bring the database up to this build."""
    outstanding = pending(context.store.db)
    if not outstanding:
        click.echo(f"already at version {current_version(context.store.db)}")
        return
    if dry_run:
        click.echo(bullets(item.describe() for item in outstanding))
        return
    applied = migrate(context.store.db, context.now())
    click.echo(bullets(item.describe() for item in applied))
    click.echo(f"now at version {latest_version()}")


@admin.command("backup")
@click.argument("target", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--overwrite", is_flag=True)
@click.pass_obj
def backup(context: Context, target: Path, overwrite: bool) -> None:
    """Take a consistent copy of the database."""
    if target.exists() and not overwrite:
        raise ConflictError("that file is already there", path=str(target))
    copy = sqlite3.connect(str(target))
    try:
        context.store.db.connection.backup(copy)
    finally:
        copy.close()
    click.echo(f"backed up to {target} ({target.stat().st_size} bytes)")


@admin.command("compact")
@click.pass_obj
def compact(context: Context) -> None:
    """Reclaim space the department has deleted its way into."""
    before = context.store.db.scalar("PRAGMA page_count") or 0
    context.store.db.execute("VACUUM")
    after = context.store.db.scalar("PRAGMA page_count") or 0
    click.echo(f"{before} pages before, {after} after")


@admin.command("tables")
@click.pass_obj
def tables(context: Context) -> None:
    """Every table and how many rows are in it."""
    rows: list[list[object]] = []
    for name in context.store.db.tables():
        count = context.store.db.scalar(f"SELECT count(*) FROM {name}")
        rows.append([name, count])
    click.echo(table([Column("table"), Column("rows", align="right")], rows))


@admin.command("compliance")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.pass_obj
def compliance_report(context: Context, start: str, end: str) -> None:
    """The period report that gets pulled before an inspection."""
    report = compliance.build(context.store, parse_day(start), parse_day(end), context.settings)
    click.echo(report.render())
    if not report.clean:
        raise SystemExit(5)


@admin.command("purge")
@click.option("--years", type=int, default=7, show_default=True, help="how long records are kept")
@click.option("--apply-purge", is_flag=True, help="actually remove them")
@click.pass_obj
def purge_command(context: Context, years: int, apply_purge: bool) -> None:
    """Remove records older than the department's retention period."""
    before = retention.cutoff(context.clock.today(), years)
    counted = (
        retention.plan(context.store.db, before)
        if not apply_purge
        else retention.purge(context.store.db, before)
    )
    click.echo(counted.describe())
    if counted.empty:
        click.echo("nothing to remove")
        return
    if not apply_purge:
        click.echo("dry run, nothing was removed")


@admin.command("checkpoint")
@click.pass_obj
def checkpoint(context: Context) -> None:
    """Fold the write ahead log back into the database file."""
    mode = context.store.db.journal_mode()
    written, left = context.store.db.checkpoint()
    click.echo(pairs([("journal", mode), ("pages written", written), ("pages left", left)]))


@admin.command("settings")
@click.option(
    "--write",
    "target",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="write the current settings out as a file to edit",
)
@click.option("--overwrite", is_flag=True)
@click.pass_obj
def settings(context: Context, target: Path | None, overwrite: bool) -> None:
    """Every department number this build is running on."""
    if target is None:
        click.echo(pairs(sorted(context.settings.describe().items())))
        return
    if target.exists() and not overwrite:
        raise ConflictError("that file is already there", path=str(target))
    target.write_text(context.settings.to_toml(), encoding="utf-8")
    click.echo(f"wrote {target}")
