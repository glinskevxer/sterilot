"""Tray commands.

Registering a tray, moving it, and the floor board. The board is the one that
gets left open on a screen in the department all day, which is why it is a
count by stage rather than a list of everything.
"""

from __future__ import annotations

import click

from sterilot.assets.lifecycle import Stage, allowed_from
from sterilot.assets.tray import Ownership, TrayInstance
from sterilot.cli.context import Context
from sterilot.reporting.render import Column, pairs, table


@click.group()
def tray() -> None:
    """Physical trays and where they are."""


@tray.command("register")
@click.argument("asset")
@click.argument("code")
@click.option("--ownership", default="department", show_default=True)
@click.option("--owner", default="", help="the vendor, for a loaner or consignment set")
@click.pass_obj
def register(context: Context, asset: str, code: str, ownership: str, owner: str) -> None:
    """Put a tray into service."""
    item = TrayInstance.placed_in_service(
        asset,
        code,
        context.now(),
        context.signed_by(),
        ownership=Ownership.named(ownership),
        owner=owner,
    )
    context.store.trays.save(item)
    click.echo(f"registered {item.label()}")


@tray.command("move")
@click.argument("asset")
@click.argument("stage")
@click.option("--note", default="")
@click.pass_obj
def move(context: Context, asset: str, stage: str, note: str) -> None:
    """Move a tray to the next stage."""
    item = context.store.trays.get(asset)
    moved = item.moved_to(Stage.named(stage), context.now(), context.signed_by(), note)
    context.store.trays.save(moved)
    click.echo(f"{moved.asset} is now {moved.stage.label}")


@tray.command("show")
@click.argument("asset")
@click.option("--history/--no-history", default=True, show_default=True)
@click.pass_obj
def show(context: Context, asset: str, history: bool) -> None:
    """One tray, where it is and where it has been."""
    item = context.store.trays.get(asset)
    click.echo(
        pairs(
            [
                ("asset", item.asset),
                ("set", item.code),
                ("ownership", item.ownership.value),
                ("owner", item.owner or ""),
                ("stage", item.stage.label),
                ("since", item.since.strftime("%Y-%m-%d %H:%M")),
                ("turns", item.turns_completed()),
                ("retired", item.retired_on.isoformat() if item.retired_on else ""),
            ]
        )
    )
    if history:
        click.echo()
        click.echo(
            table(
                [Column("when"), Column("stage"), Column("by"), Column("note")],
                [
                    [
                        event.at.strftime("%Y-%m-%d %H:%M"),
                        event.stage.label,
                        event.by,
                        event.note,
                    ]
                    for event in item.history
                ],
            )
        )


@tray.command("next")
@click.argument("asset")
@click.pass_obj
def next_stages(context: Context, asset: str) -> None:
    """Where this tray is allowed to go from here."""
    item = context.store.trays.get(asset)
    for stage in sorted(allowed_from(item.stage), key=lambda item: item.value):
        click.echo(stage.value)


@tray.command("board")
@click.pass_obj
def board(context: Context) -> None:
    """How many trays are sitting in each stage."""
    counts = context.store.trays.counts_by_stage()
    click.echo(
        table(
            [Column("stage"), Column("trays", align="right")],
            [
                [stage.label, counts.get(stage, 0)]
                for stage in Stage
                if counts.get(stage, 0) or stage.is_available
            ],
        )
    )


@tray.command("of-set")
@click.argument("code")
@click.pass_obj
def of_set(context: Context, code: str) -> None:
    """Every tray built to a set code."""
    click.echo(
        table(
            [Column("asset"), Column("stage"), Column("since")],
            [
                [item.asset, item.stage.label, item.since.strftime("%Y-%m-%d %H:%M")]
                for item in context.store.trays.of_code(code)
            ],
        )
    )
