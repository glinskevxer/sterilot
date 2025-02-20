"""Sterile storage commands.

Defining a shelf, putting packs on it, recording what happens to them, and
picking oldest first. The location check is worth running on a new shelf before
anything goes on it, because moving a rack afterwards means moving everything
that is on it.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.ids import LotControlNumber
from sterilot.reporting.render import Column, bullets, pairs, table
from sterilot.storage.event import Event, EventRecord, Package, Packaging
from sterilot.storage.shelf import Location, ParLevel, Zone


@click.group()
def shelf() -> None:
    """Sterile storage."""


@shelf.command("add-location")
@click.argument("code")
@click.argument("description")
@click.option("--zone", default="sterile_store", show_default=True)
@click.option("--units", type=int, required=True, help="how much it holds")
@click.option("--floor-cm", type=float, required=True)
@click.option("--sprinkler-cm", type=float, required=True)
@click.option("--wall-cm", type=float, default=10.0, show_default=True)
@click.option("--under-plumbing", is_flag=True)
@click.pass_obj
def add_location(
    context: Context,
    code: str,
    description: str,
    zone: str,
    units: int,
    floor_cm: float,
    sprinkler_cm: float,
    wall_cm: float,
    under_plumbing: bool,
) -> None:
    """Define a storage location, and say whether it is fit to be one."""
    place = Location(
        code=code,
        description=description,
        zone=Zone.named(zone),
        capacity_units=units,
        floor_clearance_cm=floor_cm,
        sprinkler_clearance_cm=sprinkler_cm,
        outside_wall_clearance_cm=wall_cm,
        under_plumbing=under_plumbing,
    )
    context.store.packages.save_location(place)
    click.echo(f"saved {place.label()}")
    problems = place.problems()
    if problems:
        click.echo(bullets(problems))


@shelf.command("par")
@click.argument("code")
@click.option("--minimum", type=int, required=True)
@click.option("--target", type=int, required=True)
@click.pass_obj
def par(context: Context, code: str, minimum: int, target: int) -> None:
    """Set the par level for a set."""
    level = ParLevel(code, minimum, target)
    context.store.packages.save_par(level)
    click.echo(f"{level.code} par {level.minimum} to {level.target}")


@shelf.command("put")
@click.argument("asset")
@click.argument("lot")
@click.option("--location", required=True)
@click.option("--set", "code", required=True)
@click.option("--packaging", default="sequential_wrap", show_default=True)
@click.pass_obj
def put(context: Context, asset: str, lot: str, location: str, code: str, packaging: str) -> None:
    """Put a package on a shelf."""
    number = LotControlNumber.parse(lot)
    cycle = context.store.cycles.get(number)
    package = Package(
        asset=asset,
        lot=number,
        packaging=Packaging.named(packaging),
        sterilized_at=cycle.started_at,
    )
    context.store.packages.shelve(package, location, code)
    click.echo(f"{package.label()} on {location.upper()}")


@shelf.command("event")
@click.argument("asset")
@click.argument("lot")
@click.argument("event_name")
@click.option("--note", default="")
@click.pass_obj
def record_event(context: Context, asset: str, lot: str, event_name: str, note: str) -> None:
    """Record something that happened to a package."""
    number = LotControlNumber.parse(lot)
    record = EventRecord(Event.named(event_name), context.now(), context.signed_by(), note)
    context.store.packages.record_event(asset, number, record)
    click.echo(record.describe())


@shelf.command("stock")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def stock(context: Context, on_day: str | None) -> None:
    """What is on the shelf, and what needs building."""
    now = context.now()
    if on_day:
        parse_day(on_day)
    counts = context.store.packages.on_hand(now, context.settings)
    plan = context.store.packages.storage_map()
    wanted = plan.build_list(counts)
    click.echo(
        table(
            [Column("set"), Column("on hand", align="right"), Column("build", align="right")],
            [
                [code, counts.get(code, 0), dict(wanted).get(code, 0)]
                for code in sorted(set(counts) | {item[0] for item in wanted})
            ],
        )
    )


@shelf.command("pick")
@click.argument("code")
@click.option("--quantity", type=int, default=1, show_default=True)
@click.pass_obj
def pick(context: Context, code: str, quantity: int) -> None:
    """Take packs off the shelf, oldest first."""
    result = context.store.packages.pick(code, quantity, context.now(), context.settings)
    click.echo(result.summary())
    for asset in result.assets():
        click.echo(f"  {asset}")
    if result.skipped:
        click.echo()
        click.echo(bullets(item.describe() for item in result.skipped))
    if not result.complete:
        raise SystemExit(3)


@shelf.command("check")
@click.pass_obj
def check(context: Context) -> None:
    """Every location that should not be holding sterile packages."""
    plan = context.store.packages.storage_map()
    click.echo(pairs([("locations", len(plan.locations)), ("usable capacity", plan.capacity())]))
    unusable = plan.unusable()
    if not unusable:
        click.echo("every location is fit for storage")
        return
    click.echo()
    for place in unusable:
        click.echo(place.label())
        click.echo(bullets(place.problems()))
