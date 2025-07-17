"""The root command.

Errors are not tracebacks. Every failure the package raises carries an exit
status, and the top level turns it into that status and one line on standard
error, so a script calling sterilot can tell a missing record from a rule that
refused.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from sterilot import __version__
from sterilot.cli.admin_cmd import admin
from sterilot.cli.cart_cmd import cart
from sterilot.cli.case_cmd import case
from sterilot.cli.catalog_cmd import catalog
from sterilot.cli.container_cmd import container
from sterilot.cli.context import Context, default_db_path
from sterilot.cli.count_cmd import count
from sterilot.cli.cycle_cmd import cycle
from sterilot.cli.decon_cmd import decon
from sterilot.cli.duty_cmd import duty
from sterilot.cli.export_cmd import export_group
from sterilot.cli.load_cmd import load
from sterilot.cli.loaner_cmd import loaner
from sterilot.cli.machine_cmd import machine
from sterilot.cli.maintenance_cmd import maintenance
from sterilot.cli.quality_cmd import quality
from sterilot.cli.recall_cmd import recall
from sterilot.cli.repair_cmd import repair
from sterilot.cli.report_cmd import report
from sterilot.cli.schedule_cmd import schedule
from sterilot.cli.sheet_cmd import sheet
from sterilot.cli.shelf_cmd import shelf
from sterilot.cli.staff_cmd import staff
from sterilot.cli.tray_cmd import tray
from sterilot.cli.verify_cmd import verify
from sterilot.cli.wash_cmd import wash
from sterilot.clock import parse_day
from sterilot.errors import SterilotError
from sterilot.reporting.board import build as build_board
from sterilot.reporting.doctor import check as check_department
from sterilot.reporting.render import pairs


class Cli(click.Group):
    """A group that turns our errors into exit statuses."""

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except SterilotError as error:
            click.echo(f"sterilot: {error}", err=True)
            ctx.exit(error.exit_status)


@click.group(cls=Cli)
@click.option(
    "--db",
    "db_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="the sterilot database file",
)
@click.option(
    "--settings",
    "settings_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="a settings file to read instead of the defaults",
)
@click.option("--badge", default=None, help="the badge signing anything this command writes")
@click.option(
    "--no-migrate",
    is_flag=True,
    help="open the file without bringing its schema up to this build",
)
@click.version_option(__version__, prog_name="sterilot")
@click.pass_context
def main(
    ctx: click.Context,
    db_path: Path | None,
    settings_path: Path | None,
    badge: str | None,
    no_migrate: bool,
) -> None:
    """Sterile processing records."""
    ctx.obj = Context.build(db_path, settings_path, badge, apply_migrations=not no_migrate)
    ctx.call_on_close(ctx.obj.close)


@main.command()
@click.pass_obj
def status(context: Context) -> None:
    """Where the database is and whether it is healthy."""
    problems = context.store.health()
    click.echo(
        pairs(
            [
                ("database", context.store.db.path),
                ("schema", context.store.version),
                ("facility", context.settings.facility),
                ("badge", context.badge or "not set"),
                ("health", "ok" if not problems else f"{len(problems)} problems"),
            ]
        )
    )
    for problem in problems:
        click.echo(f"  {problem}")


@main.command()
@click.pass_obj
def health(context: Context) -> None:
    """Check the file and exit non zero when something is wrong."""
    problems = context.store.health()
    if not problems:
        click.echo("no problems found")
        return
    for problem in problems:
        click.echo(problem, err=True)
    raise SystemExit(6)


@main.command()
@click.option("--on", "on_day", default=None, help="the day to check, defaults to today")
@click.pass_obj
def doctor(context: Context, on_day: str | None) -> None:
    """Everything the department is behind on."""
    day = parse_day(on_day) if on_day else context.clock.today()
    report = check_department(context.store, day, context.settings)
    click.echo(report.render())
    if report.stops:
        raise SystemExit(5)


@main.command()
@click.pass_obj
def board(context: Context) -> None:
    """Where the work is right now."""
    click.echo(build_board(context.store, context.now(), context.settings).render())


@main.command(name="where")
def where() -> None:
    """Print the database path this build would use by default."""
    click.echo(str(default_db_path()))


main.add_command(admin)
main.add_command(cart)
main.add_command(case)
main.add_command(catalog)
main.add_command(container)
main.add_command(count)
main.add_command(cycle)
main.add_command(decon)
main.add_command(duty)
main.add_command(export_group, name="export")
main.add_command(load)
main.add_command(loaner)
main.add_command(quality)
main.add_command(recall)
main.add_command(repair)
main.add_command(report)
main.add_command(schedule)
main.add_command(shelf)
main.add_command(sheet)
main.add_command(staff)
main.add_command(machine)
main.add_command(maintenance)
main.add_command(tray)
main.add_command(verify)
main.add_command(wash)


def run() -> None:  # pragma: no cover
    """Entry point wrapper, kept so the console script has a stable name."""
    sys.exit(main())
