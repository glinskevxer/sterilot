"""Container commands.

Containers are the only asset in the department that consumes something every
time it runs, so the filter count is a command rather than a footnote. The
inspection list is the other half: a container is only as good as its last look
at the gasket.
"""

from __future__ import annotations

import click

from sterilot.assets.container import Container, FilterType
from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.methods import Method
from sterilot.reporting.render import Column, bullets, pairs, table


@click.group()
def container() -> None:
    """Rigid containers and their filters."""


@container.command("add")
@click.argument("asset")
@click.option("--model", required=True)
@click.option("--manufacturer", required=True)
@click.option("--filter", "filter_type", default="synthetic", show_default=True)
@click.option("--vents", type=int, default=2, show_default=True)
@click.option("--inspected", "last_inspection", default=None)
@click.pass_obj
def add(
    context: Context,
    asset: str,
    model: str,
    manufacturer: str,
    filter_type: str,
    vents: int,
    last_inspection: str | None,
) -> None:
    """Register a container."""
    made = Container(
        asset=asset,
        model=model,
        manufacturer=manufacturer,
        filter_type=FilterType.named(filter_type),
        filter_positions=vents,
        last_inspection=parse_day(last_inspection) if last_inspection else None,
    )
    context.store.containers.save(made)
    click.echo(f"registered {made.label()}")


@container.command("show")
@click.argument("asset")
@click.pass_obj
def show(context: Context, asset: str) -> None:
    """One container and what it can run today."""
    day = context.clock.today()
    found = context.store.containers.get(asset)
    click.echo(
        pairs(
            [
                ("asset", found.asset),
                ("model", found.model),
                ("filter", found.filter_type.label),
                ("filters per cycle", found.filters_per_cycle),
                ("cycles since inspection", found.cycles_since_inspection),
                ("inspection due", found.inspection_due(day)),
                ("state", found.refusal_on_any_method(day) or "ready"),
            ]
        )
    )
    methods = found.methods(day)
    if methods:
        click.echo()
        click.echo("runs: " + ", ".join(method.value for method in methods))
    refused = [
        f"{method.label}: {found.refusal_for(method, day)}"
        for method in Method
        if not found.usable_for(method, day)
    ]
    if refused:
        click.echo()
        click.echo(bullets(refused))


@container.command("used")
@click.argument("asset")
@click.pass_obj
def used(context: Context, asset: str) -> None:
    """Record a container going through a cycle."""
    found = context.store.containers.used(asset)
    click.echo(
        f"{found.asset} has run {found.cycles_since_inspection} cycles since its last inspection"
    )
    if found.inspection_due(context.clock.today()):
        click.echo("inspection is due")


@container.command("inspect")
@click.argument("asset")
@click.option("--gasket-damaged", is_flag=True)
@click.option("--latch-damaged", is_flag=True)
@click.pass_obj
def inspect(context: Context, asset: str, gasket_damaged: bool, latch_damaged: bool) -> None:
    """Record an inspection."""
    found = context.store.containers.inspected(
        asset,
        context.clock.today(),
        gasket_intact=not gasket_damaged,
        latches_intact=not latch_damaged,
    )
    click.echo(f"{found.asset} inspected")
    refusal = found.refusal_on_any_method(context.clock.today())
    if refusal:
        click.echo(refusal)


@container.command("list")
@click.pass_obj
def list_containers(context: Context) -> None:
    """Every container and where it stands."""
    day = context.clock.today()
    click.echo(
        table(
            [
                Column("asset"),
                Column("model"),
                Column("filter"),
                Column("cycles", align="right"),
                Column("state"),
            ],
            [
                [
                    item.asset,
                    item.model,
                    item.filter_type.label,
                    item.cycles_since_inspection,
                    item.refusal_on_any_method(day) or "ready",
                ]
                for item in context.store.containers.all()
            ],
        )
    )


@container.command("due")
@click.pass_obj
def due(context: Context) -> None:
    """Containers due for inspection."""
    day = context.clock.today()
    found = context.store.containers.due_for_inspection(day)
    if not found:
        click.echo("nothing is due")
        return
    click.echo(
        table(
            [Column("asset"), Column("last inspection"), Column("cycles", align="right")],
            [
                [
                    item.asset,
                    item.last_inspection.isoformat() if item.last_inspection else "never",
                    item.cycles_since_inspection,
                ]
                for item in found
            ],
        )
    )


@container.command("filters")
@click.pass_obj
def filters(context: Context) -> None:
    """How many filters a full turn of the containers costs."""
    day = context.clock.today()
    click.echo(
        pairs(
            [
                ("containers", len(context.store.containers.all())),
                ("usable", len(context.store.containers.usable_for(Method.STEAM_PREVAC, day))),
                ("filters per turn", context.store.containers.filters_needed(day)),
            ]
        )
    )
