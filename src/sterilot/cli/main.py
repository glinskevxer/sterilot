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
from sterilot.cli.catalog_cmd import catalog
from sterilot.cli.context import Context, default_db_path
from sterilot.cli.cycle_cmd import cycle
from sterilot.cli.duty_cmd import duty
from sterilot.cli.load_cmd import load
from sterilot.cli.machine_cmd import machine
from sterilot.cli.recall_cmd import recall
from sterilot.cli.tray_cmd import tray
from sterilot.errors import SterilotError
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
@click.version_option(__version__, prog_name="sterilot")
@click.pass_context
def main(
    ctx: click.Context, db_path: Path | None, settings_path: Path | None, badge: str | None
) -> None:
    """Sterile processing records."""
    ctx.obj = Context.build(db_path, settings_path, badge)
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


@main.command(name="where")
def where() -> None:
    """Print the database path this build would use by default."""
    click.echo(str(default_db_path()))


main.add_command(catalog)
main.add_command(cycle)
main.add_command(duty)
main.add_command(load)
main.add_command(recall)
main.add_command(machine)
main.add_command(tray)


def run() -> None:  # pragma: no cover
    """Entry point wrapper, kept so the console script has a stable name."""
    sys.exit(main())
