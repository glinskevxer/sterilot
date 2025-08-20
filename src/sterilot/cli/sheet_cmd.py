"""Count sheet commands.

Defining a set, revising it, and reading the difference between two revisions.
The diff is the one that gets used in a meeting, because "what changed" is
always the question and nobody can answer it from two printed sheets.
"""

from __future__ import annotations

import click

from sterilot.catalog.revision import RevisionHistory
from sterilot.catalog.substitution import Substitution, SubstitutionTable
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.cli import values
from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.errors import NotFoundError
from sterilot.interval import DateRange
from sterilot.reporting.render import Column, bullets, table


def _lines(context: Context, given: tuple[str, ...]) -> list[CountLine]:
    lines: list[CountLine] = []
    for entry in given:
        catalog, quantity, position = values.triple(entry)
        lines.append(
            CountLine(
                context.store.catalog.instrument(catalog),
                values.whole(quantity),
                position,
            )
        )
    return lines


@click.group()
def sheet() -> None:
    """Count sheets and their revisions."""


@sheet.command("define")
@click.argument("code")
@click.argument("name")
@click.option("--line", "values", multiple=True, required=True, help="CATALOG=QTY[:POSITION]")
@click.option("--container", default=None)
@click.option("--from", "effective", required=True, help="the day it comes into force")
@click.option("--note", default="")
@click.pass_obj
def define(
    context: Context,
    code: str,
    name: str,
    values: tuple[str, ...],
    container: str | None,
    effective: str,
    note: str,
) -> None:
    """Define a set for the first time."""
    if (
        context.store.catalog.set_codes()
        and code.strip().upper() in context.store.catalog.set_codes()
    ):
        raise click.ClickException(f"{code.upper()} is already defined, use revise")
    made = CountSheet.of(code, name, _lines(context, values), container)
    context.store.catalog.save_history(RevisionHistory.started(made, parse_day(effective), note))
    click.echo(f"{made.label()} defined with {made.item_count} pieces")


@sheet.command("revise")
@click.argument("code")
@click.option("--line", "values", multiple=True, required=True, help="CATALOG=QTY[:POSITION]")
@click.option("--from", "effective", required=True)
@click.option("--note", default="")
@click.pass_obj
def revise(context: Context, code: str, values: tuple[str, ...], effective: str, note: str) -> None:
    """Close the current revision and open the next one."""
    history = context.store.catalog.history(code)
    current = history.current.sheet
    made = CountSheet.of(current.code, current.name, _lines(context, values), current.container)
    grown = history.revised(made, parse_day(effective), note)
    context.store.catalog.save_history(grown)
    click.echo(f"{grown.current.label()} in force from {effective}")


@sheet.command("diff")
@click.argument("code")
@click.option("--from", "earlier", type=int, required=True)
@click.option("--to", "later", type=int, required=True)
@click.pass_obj
def diff(context: Context, code: str, earlier: int, later: int) -> None:
    """What moved between two revisions."""
    history = context.store.catalog.history(code)
    changes = history.changes(earlier, later)
    if not changes:
        click.echo(f"nothing changed between revisions {earlier} and {later}")
        return
    click.echo(bullets(change.describe() for change in changes))


@sheet.command("history")
@click.argument("code")
@click.pass_obj
def history(context: Context, code: str) -> None:
    """Every revision of a set."""
    found = context.store.catalog.history(code)
    click.echo(
        table(
            [
                Column("revision", align="right"),
                Column("in force"),
                Column("pieces", align="right"),
                Column("note"),
            ],
            [
                [
                    revision.number,
                    revision.effective.format(),
                    revision.sheet.item_count,
                    revision.note,
                ]
                for revision in found.revisions
            ],
        )
    )


@sheet.command("substitute")
@click.argument("original")
@click.argument("replacement")
@click.option("--from", "effective", required=True)
@click.option("--to", "until", default=None)
@click.option("--ratio", type=int, default=1, show_default=True)
@click.option("--reason", default="")
@click.pass_obj
def substitute(
    context: Context,
    original: str,
    replacement: str,
    effective: str,
    until: str | None,
    ratio: int,
    reason: str,
) -> None:
    """Approve a substitution."""
    for catalog in (original, replacement):
        context.store.catalog.instrument(catalog)
    window = DateRange(parse_day(effective), parse_day(until) if until else None)
    entry = Substitution(original, replacement, context.signed_by(), window, ratio, reason)
    table_now = context.store.catalog.substitutions()
    context.store.catalog.save_substitutions(SubstitutionTable((*table_now.entries, entry)))
    click.echo(entry.describe())


@sheet.command("substitutions")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def substitutions(context: Context, on_day: str | None) -> None:
    """Every approval in force on a day."""
    day = context.day(on_day)
    found = context.store.catalog.substitutions().active(day)
    click.echo(
        table(
            [
                Column("original"),
                Column("replacement"),
                Column("ratio", align="right"),
                Column("reason"),
            ],
            [[item.original, item.replacement, item.ratio, item.reason] for item in found],
        )
    )


@sheet.command("check")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def check(context: Context, on_day: str | None) -> None:
    """Every inconsistency between the catalog, the sheets and the approvals."""
    day = context.day(on_day)
    problems: list[str] = []
    for code in context.store.catalog.set_codes():
        try:
            found = context.store.catalog.sheet(code, day)
        except NotFoundError:
            continue
        if not found.methods():
            problems.append(f"{code} has no sterilization method its contents all tolerate")
        problems.extend(
            f"{code} is missing a weight for {catalog}" for catalog in found.weights_missing()
        )
    if not problems:
        click.echo("no problems found")
        return
    click.echo(bullets(problems))
