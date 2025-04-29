"""Schedule commands.

Reading theatre's list, and turning it into the two questions the department
actually has: what has to be built, and what is on the list that we cannot pick
for because nobody attached a card.
"""

from __future__ import annotations

from pathlib import Path

import click

from sterilot.cases.preference_card import CardLine, PreferenceCard
from sterilot.cases.schedule import ScheduledCase
from sterilot.cli.context import Context
from sterilot.clock import parse_day, parse_moment
from sterilot.ingest.theatre_list import load_theatre_list
from sterilot.interval import DateRange
from sterilot.reporting.render import Column, bullets, pairs, table


@click.group()
def schedule() -> None:
    """The theatre list and the cards it is picked from."""


@schedule.command("add-case")
@click.argument("case_reference")
@click.option("--room", required=True)
@click.option("--surgeon", required=True)
@click.option("--procedure", required=True)
@click.option("--start", required=True)
@click.option("--minutes", type=int, required=True)
@click.option("--card", "card_reference", default="")
@click.pass_obj
def add_case(
    context: Context,
    case_reference: str,
    room: str,
    surgeon: str,
    procedure: str,
    start: str,
    minutes: int,
    card_reference: str,
) -> None:
    """Put a case on the list."""
    made = ScheduledCase(
        case=case_reference,
        room=room,
        surgeon=surgeon,
        procedure=procedure,
        starts_at=parse_moment(start),
        minutes=minutes,
        card_reference=card_reference,
    )
    context.store.schedule.save_case(made)
    click.echo(f"{made.case} {made.describe()}")


@schedule.command("add-card")
@click.argument("reference")
@click.option("--surgeon", required=True)
@click.option("--procedure", required=True)
@click.option("--line", "values", multiple=True, required=True, help="SET=QTY[:preferred]")
@click.option("--from", "effective", required=True)
@click.option("--loaner", "loaners", multiple=True)
@click.pass_obj
def add_card(
    context: Context,
    reference: str,
    surgeon: str,
    procedure: str,
    values: tuple[str, ...],
    effective: str,
    loaners: tuple[str, ...],
) -> None:
    """Write a preference card."""
    lines = []
    for value in values:
        code, _, rest = value.partition("=")
        quantity, _, weight = rest.partition(":")
        lines.append(CardLine(code, int(quantity or 1), weight.strip().lower() != "preferred"))
    card = PreferenceCard.of(
        reference,
        surgeon,
        procedure,
        lines,
        DateRange.starting(parse_day(effective)),
        loaner_sets=loaners,
    )
    context.store.schedule.save_card(card)
    click.echo(f"{card.label()} calls for {card.total_sets} sets")


@schedule.command("import")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="read the file without saving anything")
@click.pass_obj
def import_list(context: Context, path: Path, dry_run: bool) -> None:
    """Read a theatre export and put its cases on the list."""
    result = load_theatre_list(path.read_text(encoding="utf-8"))
    if not dry_run:
        for case in result.cases:
            context.store.schedule.save_case(case)
    click.echo(result.summary())
    if result.rooms():
        click.echo("rooms: " + ", ".join(result.rooms()))
    if dry_run:
        click.echo("dry run, nothing was saved")
    if result.problems:
        click.echo(bullets(item.describe() for item in result.problems))
        raise SystemExit(2)


@schedule.command("day")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def day(context: Context, on_day: str | None) -> None:
    """The list for a day, room by room."""
    wanted = parse_day(on_day) if on_day else context.clock.today()
    found = context.store.schedule.schedule(wanted)
    click.echo(
        table(
            [
                Column("case"),
                Column("room"),
                Column("start"),
                Column("surgeon"),
                Column("procedure"),
                Column("card"),
            ],
            [
                [
                    item.case,
                    item.room,
                    item.starts_at.strftime("%H:%M"),
                    item.surgeon,
                    item.procedure,
                    item.card_reference or "none",
                ]
                for item in found.on_day(wanted)
            ],
        )
    )
    overlaps = found.overlaps(wanted)
    if overlaps:
        click.echo()
        click.echo(
            bullets(
                f"{first.case} and {second.case} share {first.room}" for first, second in overlaps
            )
        )


@schedule.command("demand")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def demand(context: Context, on_day: str | None) -> None:
    """What the day's list calls for, against what is on the shelf."""
    wanted = parse_day(on_day) if on_day else context.clock.today()
    found = context.store.schedule.schedule(wanted)
    needed = found.demand(context.store.schedule.cards(), wanted)
    on_hand = context.store.packages.on_hand(context.now(), context.settings)
    click.echo(
        table(
            [
                Column("set"),
                Column("needed", align="right"),
                Column("on hand", align="right"),
                Column("short", align="right"),
            ],
            [
                [code, count, on_hand.get(code, 0), max(count - on_hand.get(code, 0), 0)]
                for code, count in sorted(needed.items())
            ],
        )
    )
    loose = found.unattached(wanted)
    if loose:
        click.echo()
        click.echo(bullets(f"{item.case} has no preference card" for item in loose))


@schedule.command("case")
@click.argument("case_reference")
@click.pass_obj
def show_case(context: Context, case_reference: str) -> None:
    """One case, and what it calls for."""
    found = context.store.schedule.case(case_reference)
    click.echo(
        pairs(
            [
                ("case", found.case),
                ("room", found.room),
                ("surgeon", found.surgeon),
                ("procedure", found.procedure),
                ("starts", found.starts_at.strftime("%Y-%m-%d %H:%M")),
                ("trays due", found.ready_by().strftime("%H:%M")),
                ("card", found.card_reference or "none"),
            ]
        )
    )
    if not found.card_reference:
        return
    card = context.store.schedule.card(found.card_reference, found.day)
    click.echo()
    click.echo(bullets(line.describe() for line in card.lines))
