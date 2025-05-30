"""Counting a tray at the assembly bench.

The count is given as catalog numbers and quantities, the sheet is the one that
was in force on the day, and the approval list decides whether a replacement in
the tray covers a shortage or is a foreign instrument.

A tray that comes up short can raise its own exception, because the alternative
is that somebody means to and the shift ends first.
"""

from __future__ import annotations

import click

from sterilot.catalog.count import count_tray
from sterilot.cli import values
from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.quality.audit import Action
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.reporting.render import Column, bullets, pairs, table


@click.group()
def count() -> None:
    """Counting trays against their sheets."""


@count.command("tray")
@click.argument("code")
@click.option("--item", "items", multiple=True, required=True, help="CATALOG=QTY, repeatable")
@click.option("--on", "on_day", default=None, help="the day the sheet was in force")
@click.option("--asset", default="", help="the tray being counted, for an exception")
@click.option("--raise-exception", "reference", default="", help="raise one if the count is short")
@click.pass_obj
def tray(
    context: Context,
    code: str,
    items: tuple[str, ...],
    on_day: str | None,
    asset: str,
    reference: str,
) -> None:
    """Reconcile a counted tray against its sheet."""
    day = parse_day(on_day) if on_day else context.clock.today()
    sheet = context.store.catalog.sheet(code, day)
    approvals = context.store.catalog.substitutions()
    result = count_tray(sheet, values.tally(items), approvals, day)
    click.echo(result.summary())
    if result.substitutions:
        click.echo()
        click.echo(bullets(item.describe() for item in result.substitutions))
    if result.complete:
        return
    if reference:
        entry = Nonconformance(
            reference=reference,
            category=Category.ASSEMBLY,
            severity=Severity.MINOR,
            raised_at=context.now(),
            raised_by=context.signed_by(),
            description=result.summary(),
            subject=asset or sheet.code,
        )
        context.store.quality.save_exception(entry)
        context.store.quality.record(
            context.now(), entry.raised_by, Action.RECORDED, "exception", entry.reference
        )
        click.echo()
        click.echo(f"raised {entry.reference}")
    raise SystemExit(5)


@count.command("sheet")
@click.argument("code")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def show_sheet(context: Context, code: str, on_day: str | None) -> None:
    """What the bench should be counting."""
    day = parse_day(on_day) if on_day else context.clock.today()
    sheet = context.store.catalog.sheet(code, day)
    click.echo(
        pairs(
            [
                ("set", sheet.label()),
                ("pieces", sheet.item_count),
                ("required", sheet.required_count),
                ("sink minutes", f"{sheet.sink_minutes():.0f}"),
                ("known weight", sheet.known_weight().format()),
            ]
        )
    )
    click.echo()
    click.echo(
        table(
            [
                Column("catalog"),
                Column("description"),
                Column("qty", align="right"),
                Column("position"),
                Column("required"),
            ],
            [
                [
                    line.catalog,
                    line.instrument.description,
                    line.quantity,
                    line.position,
                    line.required,
                ]
                for line in sheet.lines
            ],
        )
    )
