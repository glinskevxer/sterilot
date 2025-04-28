"""Case cart commands.

Building a cart is picking from the shelf against a card, which is why the pick
and the check happen in the same command. A cart that comes up short says so at
half past six rather than at the door of the room.
"""

from __future__ import annotations

import click

from sterilot.cases.cart import CartLine, CaseCart
from sterilot.cli.context import Context
from sterilot.reporting.render import Column, bullets, pairs, table


@click.group()
def cart() -> None:
    """Case carts."""


@cart.command("build")
@click.argument("reference")
@click.argument("case_reference")
@click.pass_obj
def build(context: Context, reference: str, case_reference: str) -> None:
    """Pick a cart from the shelf against the case's card."""
    scheduled = context.store.schedule.case(case_reference)
    if not scheduled.card_reference:
        raise click.ClickException(f"{scheduled.case} has no preference card")
    card = context.store.schedule.card(scheduled.card_reference, scheduled.day)
    lines: list[CartLine] = []
    skipped: list[str] = []
    for code, quantity in card.wanted().items():
        result = context.store.packages.pick(code, quantity, context.now(), context.settings)
        for item in result.picked:
            lines.append(CartLine(item.asset, item.code, item.location, context.signed_by()))
        skipped.extend(item.describe() for item in result.skipped)
        if not result.complete:
            skipped.append(f"{code} came up {result.short} short")
    made = CaseCart.of(
        reference, scheduled.case, card.reference, lines, context.signed_by(), context.now()
    )
    context.store.carts.save(made)
    click.echo(made.summary(card))
    if skipped:
        click.echo()
        click.echo(bullets(skipped))
    if not made.ready(card):
        raise SystemExit(5)


@cart.command("add")
@click.argument("reference")
@click.option("--tray", "trays", multiple=True, required=True)
@click.pass_obj
def add(context: Context, reference: str, trays: tuple[str, ...]) -> None:
    """Put more trays on a cart that has already been built."""
    made = context.store.carts.get(reference)
    lines = list(made.lines)
    for asset in trays:
        tray = context.store.trays.get(asset)
        lines.append(CartLine(tray.asset, tray.code, "", context.signed_by()))
    grown = CaseCart.of(
        made.reference,
        made.case,
        made.card_reference,
        lines,
        made.built_by,
        made.built_at,
        made.delivered_at,
    )
    context.store.carts.save(grown)
    click.echo(f"{grown.reference} now carries {len(grown.lines)} trays")


@cart.command("check")
@click.argument("reference")
@click.pass_obj
def check(context: Context, reference: str) -> None:
    """Compare a cart against the card it was built from."""
    made = context.store.carts.get(reference)
    scheduled = context.store.schedule.case(made.case)
    card = context.store.schedule.card(made.card_reference, scheduled.day)
    gaps = made.gaps(card)
    click.echo(made.summary(card))
    if not gaps:
        return
    click.echo()
    click.echo(bullets(gap.describe() for gap in gaps))
    if made.blocking_gaps(card):
        raise SystemExit(5)


@cart.command("deliver")
@click.argument("reference")
@click.pass_obj
def deliver(context: Context, reference: str) -> None:
    """Record a cart going to the room."""
    made = context.store.carts.get(reference).delivered_on(context.now())
    context.store.carts.save(made)
    click.echo(f"{made.reference} delivered to {made.case}")


@cart.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """One cart and what is on it."""
    made = context.store.carts.get(reference)
    click.echo(
        pairs(
            [
                ("reference", made.reference),
                ("case", made.case),
                ("card", made.card_reference),
                ("built", made.built_at.strftime("%Y-%m-%d %H:%M")),
                ("by", made.built_by),
                ("delivered", made.delivered),
            ]
        )
    )
    click.echo()
    click.echo(
        table(
            [Column("tray"), Column("set"), Column("from"), Column("picked by")],
            [[line.asset, line.code, line.location, line.picked_by] for line in made.lines],
        )
    )


@cart.command("waiting")
@click.pass_obj
def waiting(context: Context) -> None:
    """Every cart built and not yet delivered."""
    click.echo(
        table(
            [Column("reference"), Column("case"), Column("trays", align="right"), Column("built")],
            [
                [item.reference, item.case, len(item.lines), item.built_at.strftime("%H:%M")]
                for item in context.store.carts.undelivered()
            ],
        )
    )
