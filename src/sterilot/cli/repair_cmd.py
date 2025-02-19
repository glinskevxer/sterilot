"""Repair commands.

Raising an order, moving it along, and the question the assembly bench asks
every morning: which sets are short because something is at the vendor.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.money import Money
from sterilot.repair.order import RepairOrder, Status
from sterilot.reporting.render import Column, pairs, table


@click.group()
def repair() -> None:
    """Instruments away for repair."""


@repair.command("raise")
@click.argument("reference")
@click.argument("asset")
@click.option("--catalog", required=True)
@click.option("--from-set", "out_of", required=True, help="the set it came out of")
@click.option("--vendor", required=True)
@click.option("--fault", required=True)
@click.pass_obj
def raise_order(
    context: Context,
    reference: str,
    asset: str,
    catalog: str,
    out_of: str,
    vendor: str,
    fault: str,
) -> None:
    """Raise a repair order."""
    order = RepairOrder(
        reference=reference,
        asset=asset,
        catalog=catalog,
        tray_code_out_of=out_of,
        vendor=vendor,
        fault=fault,
        raised_at=context.now(),
        raised_by=context.signed_by(),
    )
    context.store.repairs.add(order)
    click.echo(order.summary())


@repair.command("send")
@click.argument("reference")
@click.pass_obj
def send(context: Context, reference: str) -> None:
    """Send an order to the vendor."""
    order = context.store.repairs.get(reference).moved_to(Status.SENT, context.now())
    context.store.repairs.save(order)
    click.echo(order.summary())


@repair.command("quote")
@click.argument("reference")
@click.argument("amount")
@click.pass_obj
def quote(context: Context, reference: str, amount: str) -> None:
    """Record a quote from the vendor."""
    order = context.store.repairs.get(reference).moved_to(
        Status.QUOTED, context.now(), quote=Money.parse(amount)
    )
    context.store.repairs.save(order)
    click.echo(
        f"{order.summary()}, {'supervisor' if order.needs_supervisor() else 'lead'} approval"
    )


@repair.command("approve")
@click.argument("reference")
@click.pass_obj
def approve(context: Context, reference: str) -> None:
    """Approve the quote on an order."""
    order = context.store.repairs.get(reference)
    if order.quote is None:
        raise click.ClickException(f"{order.reference} has no quote to approve")
    person = context.store.staff.get(context.signed_by())
    approved = order.approved(context.now(), person, order.quote)
    context.store.repairs.save(approved)
    click.echo(approved.summary())


@repair.command("close")
@click.argument("reference")
@click.option("--as", "outcome", type=click.Choice(["returned", "scrapped"]), default="returned")
@click.pass_obj
def close(context: Context, reference: str, outcome: str) -> None:
    """Close an order when the instrument comes back, or does not."""
    order = context.store.repairs.get(reference).moved_to(Status.named(outcome), context.now())
    context.store.repairs.save(order)
    click.echo(order.summary())


@repair.command("open")
@click.pass_obj
def open_orders(context: Context) -> None:
    """Every order still running."""
    today = context.clock.today()
    click.echo(
        table(
            [
                Column("reference"),
                Column("asset"),
                Column("set"),
                Column("vendor"),
                Column("status"),
                Column("days out", align="right"),
                Column("overdue"),
            ],
            [
                [
                    order.reference,
                    order.asset,
                    order.tray_code_out_of,
                    order.vendor,
                    order.status.label,
                    order.days_out(today) if order.days_out(today) is not None else "",
                    order.overdue(today),
                ]
                for order in context.store.repairs.open_orders()
            ],
        )
    )


@repair.command("shorting")
@click.argument("code")
@click.pass_obj
def shorting(context: Context, code: str) -> None:
    """What is out of a set right now."""
    found = context.store.repairs.away_from(code)
    if not found:
        click.echo(f"nothing is out of {code.upper()}")
        return
    click.echo(
        table(
            [Column("reference"), Column("asset"), Column("catalog"), Column("fault")],
            [[order.reference, order.asset, order.catalog, order.fault] for order in found],
        )
    )


@repair.command("spend")
@click.pass_obj
def spend(context: Context) -> None:
    """What has been committed to the repair bench."""
    book = context.store.repairs.book()
    click.echo(
        pairs(
            [
                ("orders", len(book.orders)),
                ("open", len(book.open_orders())),
                ("committed", book.spend().format()),
            ]
        )
    )
