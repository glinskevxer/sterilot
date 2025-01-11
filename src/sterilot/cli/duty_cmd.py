"""Daily test commands.

Logging the morning tests and asking whether anything is missing. The gap
report is deliberately driven by the days a machine actually ran rather than by
the calendar, because a chamber that was off all week owes nothing.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.interval import DateRange
from sterilot.quality.log import Duty, LogEntry, duties_for_sterilizer, duties_for_washer
from sterilot.reporting.render import Column, table


@click.group()
def duty() -> None:
    """The daily tests every machine owes."""


@duty.command("log")
@click.argument("equipment")
@click.argument("duty_name")
@click.option("--on", "on_day", default=None)
@click.option("--failed", is_flag=True, help="record a failure instead of a pass")
@click.option("--note", default="")
@click.pass_obj
def log(
    context: Context, equipment: str, duty_name: str, on_day: str | None, failed: bool, note: str
) -> None:
    """Record one daily test."""
    day = parse_day(on_day) if on_day else context.clock.today()
    entry = LogEntry(
        day=day,
        equipment=equipment,
        duty=Duty.named(duty_name),
        passed=not failed,
        by=context.signed_by(),
        note=note,
    )
    context.store.duties.save(entry)
    click.echo(entry.describe())


@duty.command("day")
@click.argument("equipment")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def day(context: Context, equipment: str, on_day: str | None) -> None:
    """What has been logged for a machine on a day, and what is still owed."""
    wanted = parse_day(on_day) if on_day else context.clock.today()
    kind = context.store.equipment.kind_of(equipment)
    if kind == "sterilizer":
        owed = duties_for_sterilizer(context.store.equipment.sterilizer(equipment))
    else:
        owed = duties_for_washer(context.store.equipment.washer(equipment))
    logged = context.store.duties.on_day(equipment, wanted)
    click.echo(
        table(
            [Column("duty"), Column("result"), Column("by"), Column("note")],
            [
                [entry.duty.label, "pass" if entry.passed else "FAIL", entry.by, entry.note]
                for entry in logged
            ],
        )
    )
    done = {entry.duty for entry in logged if entry.passed}
    missing = sorted(owed - done, key=lambda item: item.value)
    if missing:
        click.echo()
        click.echo("still owed: " + ", ".join(item.label for item in missing))


@duty.command("failures")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.pass_obj
def failures(context: Context, start: str, end: str) -> None:
    """Every failed daily test in a window."""
    window = DateRange(parse_day(start), parse_day(end))
    assert window.end is not None
    found = context.store.duties.failures(window.start, window.end)
    click.echo(
        table(
            [Column("day"), Column("machine"), Column("duty"), Column("note")],
            [
                [entry.day.isoformat(), entry.equipment, entry.duty.label, entry.note]
                for entry in found
            ],
        )
    )
