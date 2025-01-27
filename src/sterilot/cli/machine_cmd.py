"""Machine commands.

Registering a sterilizer or a washer, and the two questions the floor asks
first thing: what can run today, and what does each chamber owe before it can.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.decon.washer import Washer, WasherClass
from sterilot.methods import Method
from sterilot.quality.log import duties_for_sterilizer, duties_for_washer
from sterilot.reporting.render import Column, pairs, table
from sterilot.sterilizer.equipment import ChamberSize, Sterilizer


@click.group()
def machine() -> None:
    """Washers and sterilizers."""


@machine.command("add-sterilizer")
@click.argument("equipment")
@click.option("--model", required=True)
@click.option("--manufacturer", required=True)
@click.option("--method", "method_names", multiple=True, required=True, help="repeatable")
@click.option("--chamber", default="single", show_default=True)
@click.option("--installed", "installed_on", default=None)
@click.pass_obj
def add_sterilizer(
    context: Context,
    equipment: str,
    model: str,
    manufacturer: str,
    method_names: tuple[str, ...],
    chamber: str,
    installed_on: str | None,
) -> None:
    """Register a sterilizer."""
    unit = Sterilizer(
        equipment=equipment,
        model=model,
        manufacturer=manufacturer,
        methods=frozenset(Method.named(name) for name in method_names),
        chamber=ChamberSize.named(chamber),
        installed_on=parse_day(installed_on) if installed_on else None,
    )
    context.store.equipment.save_sterilizer(unit)
    click.echo(f"registered {unit.label()}")


@machine.command("add-washer")
@click.argument("equipment")
@click.option("--model", required=True)
@click.option("--manufacturer", required=True)
@click.option("--class", "washer_class", default="single_chamber", show_default=True)
@click.option("--chambers", type=int, default=1, show_default=True)
@click.option("--qualified", "last_qualification", default=None)
@click.pass_obj
def add_washer(
    context: Context,
    equipment: str,
    model: str,
    manufacturer: str,
    washer_class: str,
    chambers: int,
    last_qualification: str | None,
) -> None:
    """Register a washer."""
    unit = Washer(
        equipment=equipment,
        model=model,
        manufacturer=manufacturer,
        washer_class=WasherClass.named(washer_class),
        chambers=chambers,
        last_qualification=parse_day(last_qualification) if last_qualification else None,
    )
    context.store.equipment.save_washer(unit)
    click.echo(f"registered {unit.label()}")


@machine.command("list")
@click.pass_obj
def list_machines(context: Context) -> None:
    """Every machine and whether it can run today."""
    day = context.clock.today()
    rows: list[list[object]] = []
    for unit in context.store.equipment.sterilizers():
        rows.append(
            [
                unit.equipment,
                "sterilizer",
                unit.model,
                ", ".join(sorted(method.value for method in unit.methods)),
                unit.refusal_on(day) or "ready",
            ]
        )
    for washer in context.store.equipment.washers():
        rows.append(
            [
                washer.equipment,
                "washer",
                washer.model,
                washer.washer_class.label,
                washer.refusal_on(day) or "ready",
            ]
        )
    click.echo(
        table(
            [Column("id"), Column("kind"), Column("model"), Column("runs"), Column("state")],
            rows,
        )
    )


@machine.command("duties")
@click.argument("equipment")
@click.pass_obj
def duties(context: Context, equipment: str) -> None:
    """What this machine owes on a day it runs."""
    kind = context.store.equipment.kind_of(equipment)
    if kind == "sterilizer":
        owed = duties_for_sterilizer(context.store.equipment.sterilizer(equipment))
    else:
        owed = duties_for_washer(context.store.equipment.washer(equipment))
    if not owed:
        click.echo("nothing daily")
        return
    for duty in sorted(owed, key=lambda item: item.value):
        click.echo(duty.label)


@machine.command("show")
@click.argument("equipment")
@click.pass_obj
def show(context: Context, equipment: str) -> None:
    """One machine, and why it can or cannot run."""
    day = context.clock.today()
    kind = context.store.equipment.kind_of(equipment)
    if kind == "sterilizer":
        unit = context.store.equipment.sterilizer(equipment)
        click.echo(
            pairs(
                [
                    ("id", unit.equipment),
                    ("model", unit.model),
                    ("methods", ", ".join(sorted(m.value for m in unit.methods))),
                    ("chamber", unit.chamber.value),
                    ("capacity", unit.capacity_units),
                    ("daily air removal", unit.daily_air_removal_test),
                    ("qualification runs owed", unit.qualification_runs_owed),
                    ("state", unit.refusal_on(day) or "ready"),
                ]
            )
        )
        return
    washer = context.store.equipment.washer(equipment)
    click.echo(
        pairs(
            [
                ("id", washer.equipment),
                ("model", washer.model),
                ("class", washer.washer_class.label),
                ("disinfects", washer.disinfects),
                ("qualification due", washer.qualification_due(day)),
                ("state", washer.refusal_on(day) or "ready"),
            ]
        )
    )


@machine.command("repaired")
@click.argument("equipment")
@click.pass_obj
def repaired(context: Context, equipment: str) -> None:
    """Record a repair, which puts the chamber back in the qualification queue."""
    unit = context.store.equipment.sterilizer(equipment).repaired()
    context.store.equipment.save_sterilizer(unit)
    click.echo(f"{unit.equipment} owes {unit.qualification_runs_owed} qualification runs")
