"""Planned maintenance commands."""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.reporting.render import Column, table
from sterilot.sterilizer.maintenance import Task


@click.group()
def maintenance() -> None:
    """The work that stops the unplanned kind."""


@maintenance.command("add")
@click.argument("equipment")
@click.argument("code")
@click.argument("description")
@click.option("--every-days", type=int, default=None)
@click.option("--every-cycles", type=int, default=None)
@click.option("--last-done", default=None)
@click.pass_obj
def add(
    context: Context,
    equipment: str,
    code: str,
    description: str,
    every_days: int | None,
    every_cycles: int | None,
    last_done: str | None,
) -> None:
    """Put a job on the schedule."""
    task = Task(
        code=code,
        equipment=equipment,
        description=description,
        every_days=every_days,
        every_cycles=every_cycles,
        last_done=parse_day(last_done) if last_done else None,
    )
    context.store.maintenance.save(task)
    click.echo(task.describe())


@maintenance.command("done")
@click.argument("equipment")
@click.argument("code")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def done(context: Context, equipment: str, code: str, on_day: str | None) -> None:
    """Record a job as done."""
    day = parse_day(on_day) if on_day else context.clock.today()
    task = context.store.maintenance.done(equipment, code, day)
    due = task.due_on()
    click.echo(f"{task.code} done {day.isoformat()}" + (f", next {due.isoformat()}" if due else ""))


@maintenance.command("ran")
@click.argument("equipment")
@click.pass_obj
def ran(context: Context, equipment: str) -> None:
    """Count one cycle against the cycle driven jobs on a machine."""
    changed = context.store.maintenance.after_cycle(equipment)
    if not changed:
        click.echo("no cycle driven jobs on that machine")
        return
    for task in changed:
        left = task.cycles_left()
        click.echo(f"{task.code}: {left} cycles left")


@maintenance.command("due")
@click.option("--on", "on_day", default=None)
@click.option("--within", type=int, default=0, show_default=True, help="also look ahead this far")
@click.pass_obj
def due(context: Context, on_day: str | None, within: int) -> None:
    """Everything due, and optionally what is coming."""
    day = parse_day(on_day) if on_day else context.clock.today()
    found = context.store.maintenance.due(day)
    click.echo(
        table(
            [Column("machine"), Column("task"), Column("what"), Column("why")],
            [
                [task.equipment, task.code, task.description, task.reason(day) or ""]
                for task in found
            ],
        )
    )
    if within:
        coming = context.store.maintenance.coming(day, within)
        if coming:
            click.echo()
            click.echo(
                table(
                    [Column("machine"), Column("task"), Column("due")],
                    [[task.equipment, task.code, _due_text(task)] for task in coming],
                )
            )


def _due_text(task: Task) -> str:
    due_on = task.due_on()
    return due_on.isoformat() if due_on is not None else ""


@maintenance.command("list")
@click.argument("equipment")
@click.pass_obj
def list_tasks(context: Context, equipment: str) -> None:
    """Every job on one machine."""
    for task in context.store.maintenance.for_equipment(equipment):
        click.echo(task.describe())
