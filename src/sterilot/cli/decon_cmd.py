"""Point of use and sink commands.

Both of these are recorded on the dirty side by somebody in a gown, so the
commands are short and they say plainly what is wrong rather than making
anybody read a table.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_moment
from sterilot.decon.manual import ManualClean, PointOfUse
from sterilot.errors import NotFoundError
from sterilot.reporting.render import Column, bullets, table
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


@click.group()
def decon() -> None:
    """The dirty side, before the washer."""


@decon.command("point-of-use")
@click.argument("case_reference")
@click.option("--finished", required=True, help="when the case finished")
@click.option("--collected", required=True, help="when the set was collected")
@click.option("--dry", is_flag=True, help="the set was not kept moist")
@click.option("--open-container", is_flag=True, help="it travelled in an open container")
@click.option("--soil-left", is_flag=True, help="gross soil was not removed in the room")
@click.pass_obj
def point_of_use(
    context: Context,
    case_reference: str,
    finished: str,
    collected: str,
    dry: bool,
    open_container: bool,
    soil_left: bool,
) -> None:
    """Record what the room did with a set."""
    trip = PointOfUse(
        case=case_reference,
        finished_at=parse_moment(finished),
        collected_at=parse_moment(collected),
        kept_moist=not dry,
        container_closed=not open_container,
        gross_soil_removed=not soil_left,
    )
    context.store.decon.save_trip(trip)
    click.echo(f"{trip.case} collected after {trip.delay.spelled()}")
    problems = trip.problems()
    if problems:
        click.echo(bullets(problems))
        click.echo(f"the sink soak is now {trip.soak_factor():.0f} times the usual")


@decon.command("sink")
@click.argument("catalog")
@click.option("--soak", required=True, help="how long it soaked")
@click.option("--detergent-c", type=float, required=True)
@click.option("--brush-mm", type=float, default=None)
@click.option("--passes", type=int, default=0, show_default=True)
@click.option("--disassembled", is_flag=True)
@click.option("--case", "case_reference", default="")
@click.pass_obj
def sink(
    context: Context,
    catalog: str,
    soak: str,
    detergent_c: float,
    brush_mm: float | None,
    passes: int,
    disassembled: bool,
    case_reference: str,
) -> None:
    """Record a manual clean, judged against the catalog entry."""
    item = context.store.catalog.instrument(catalog)
    record = ManualClean(
        catalog=item.catalog,
        at=context.now(),
        by=context.signed_by(),
        soaked=Duration.parse(soak, bare_unit="m"),
        detergent_temperature=Temperature(detergent_c),
        brush_mm=brush_mm,
        brush_passes=passes,
        disassembled=disassembled,
    )
    context.store.decon.save_clean(record, case_reference)
    trip = None
    if case_reference:
        try:
            trip = context.store.decon.trip(case_reference)
        except NotFoundError:
            trip = None
    problems = record.problems(item, trip)
    if not problems:
        click.echo(f"{record.catalog} cleaned")
        return
    click.echo(f"{record.catalog} cleaned, {len(problems)} problems")
    click.echo(bullets(problems))
    raise SystemExit(5)


@decon.command("day")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def day(context: Context, on_day: str | None) -> None:
    """Every set that came back today, and how the trip went."""
    wanted = context.day(on_day)
    found = context.store.decon.trips_on(wanted)
    click.echo(
        table(
            [Column("case"), Column("finished"), Column("delay"), Column("problems")],
            [
                [
                    trip.case,
                    trip.finished_at.strftime("%H:%M"),
                    trip.delay.spelled(),
                    "; ".join(trip.problems()),
                ]
                for trip in found
            ],
        )
    )


@decon.command("sink-history")
@click.argument("catalog")
@click.pass_obj
def sink_history(context: Context, catalog: str) -> None:
    """Every time an item went through the sink."""
    click.echo(
        table(
            [
                Column("when"),
                Column("by"),
                Column("soak"),
                Column("brush"),
                Column("passes", align="right"),
            ],
            [
                [
                    record.at.strftime("%Y-%m-%d %H:%M"),
                    record.by,
                    record.soaked.spelled(),
                    "" if record.brush_mm is None else f"{record.brush_mm:.1f} mm",
                    record.brush_passes,
                ]
                for record in context.store.decon.cleans_of(catalog)
            ],
        )
    )
