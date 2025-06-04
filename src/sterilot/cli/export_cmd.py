"""Export commands.

Everything an inspector or the hospital's data team asks for, as delimited
text, for a window of days. Written to standard output unless a file is named,
so it pipes.
"""

from __future__ import annotations

from pathlib import Path

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.reporting import export


def _emit(text: str, target: Path | None) -> None:
    if target is None:
        click.echo(text, nl=False)
        return
    target.write_text(text, encoding="utf-8")
    click.echo(f"wrote {len(text.splitlines()) - 1} rows to {target}")


@click.group()
def export_group() -> None:
    """Records out as delimited text."""


@export_group.command("cycles")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.option("--equipment", default=None, help="one chamber, or every chamber")
@click.option("--to-file", "target", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--delimiter", default=",", show_default=True)
@click.pass_obj
def cycles(
    context: Context,
    start: str,
    end: str,
    equipment: str | None,
    target: Path | None,
    delimiter: str,
) -> None:
    """Every sterilizer cycle in a window."""
    first, last = parse_day(start), parse_day(end)
    chambers = (
        [equipment]
        if equipment
        else [unit.equipment for unit in context.store.equipment.sterilizers()]
    )
    found = [
        cycle
        for chamber in chambers
        for cycle in context.store.cycles.between(chamber, first, last)
    ]
    found.sort(key=lambda cycle: (cycle.day, cycle.equipment, cycle.run))
    _emit(export.cycles(found, delimiter), target)


@export_group.command("loads")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.option("--to-file", "target", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--delimiter", default=",", show_default=True)
@click.pass_obj
def loads(context: Context, start: str, end: str, target: Path | None, delimiter: str) -> None:
    """Every load in a window, by the day its chamber ran."""
    found = context.store.loads.on_days(parse_day(start), parse_day(end))
    _emit(export.loads(found, delimiter), target)


@export_group.command("exceptions")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.option("--to-file", "target", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--delimiter", default=",", show_default=True)
@click.pass_obj
def exceptions(context: Context, start: str, end: str, target: Path | None, delimiter: str) -> None:
    """Every exception raised in a window."""
    found = context.store.quality.exceptions_between(parse_day(start), parse_day(end))
    _emit(export.exceptions(found, delimiter), target)
