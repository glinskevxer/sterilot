"""Catalog commands.

Adding an instrument, reading one back, and asking a set which chambers it can
go in. The last of those is the one people use: it is far quicker than reading
the instructions for use for every item on a sheet.
"""

from __future__ import annotations

import click

from sterilot.catalog.instrument import Complexity, Criticality, Instrument
from sterilot.catalog.material import material_named, standard_materials
from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.methods import Method
from sterilot.reporting.render import Column, bullets, pairs, table
from sterilot.units.mass import Mass


@click.group()
def catalog() -> None:
    """Instruments, sets and approved substitutions."""


@catalog.command("add")
@click.argument("catalog_number")
@click.argument("description")
@click.option("--manufacturer", required=True)
@click.option("--material", default="SS", show_default=True)
@click.option("--complexity", default="simple", show_default=True)
@click.option("--criticality", default="critical", show_default=True)
@click.option("--lumen-mm", type=float, default=None, help="channel diameter")
@click.option("--lumen-length-mm", type=float, default=None)
@click.option("--disassembly", is_flag=True, help="comes apart for cleaning")
@click.option("--insulated", is_flag=True, help="electrosurgical")
@click.option("--grams", type=float, default=None)
@click.pass_obj
def add(
    context: Context,
    catalog_number: str,
    description: str,
    manufacturer: str,
    material: str,
    complexity: str,
    criticality: str,
    lumen_mm: float | None,
    lumen_length_mm: float | None,
    disassembly: bool,
    insulated: bool,
    grams: float | None,
) -> None:
    """Add or replace a catalog entry."""
    item = Instrument(
        catalog=catalog_number,
        description=description,
        manufacturer=manufacturer,
        material=material_named(material),
        complexity=Complexity.named(complexity),
        criticality=Criticality.named(criticality),
        lumen_diameter_mm=lumen_mm,
        lumen_length_mm=lumen_length_mm,
        requires_disassembly=disassembly,
        insulated=insulated,
        weight=None if grams is None else Mass.of_grams(grams),
    )
    context.store.catalog.save_instrument(item)
    click.echo(f"saved {item.label()}")


@catalog.command("show")
@click.argument("catalog_number")
@click.pass_obj
def show(context: Context, catalog_number: str) -> None:
    """Everything we know about one catalog number."""
    item = context.store.catalog.instrument(catalog_number)
    click.echo(
        pairs(
            [
                ("catalog", item.catalog),
                ("description", item.description),
                ("manufacturer", item.manufacturer),
                ("material", item.material.name),
                ("complexity", item.complexity.label),
                ("criticality", item.criticality.value),
                ("lumen", "" if not item.has_lumen else f"{item.lumen_diameter_mm} mm"),
                ("sink minutes", f"{item.sink_minutes:.1f}"),
            ]
        )
    )
    click.echo()
    click.echo("methods it tolerates")
    click.echo(bullets(method.label for method in item.methods()))
    refused = [
        f"{method.label}: {item.refusal_for(method)}"
        for method in Method
        if not item.tolerates(method)
    ]
    if refused:
        click.echo()
        click.echo("methods it does not")
        click.echo(bullets(refused))


@catalog.command("list")
@click.pass_obj
def list_instruments(context: Context) -> None:
    """Every catalog entry we stock."""
    items = context.store.catalog.instruments()
    click.echo(
        table(
            [Column("catalog"), Column("description"), Column("material"), Column("complexity")],
            [
                [item.catalog, item.description, item.material.code, item.complexity.label]
                for item in items
            ],
        )
    )


@catalog.command("materials")
def materials() -> None:
    """The material list and what each one survives."""
    click.echo(
        table(
            [Column("code"), Column("material"), Column("methods")],
            [
                [item.code, item.name, ", ".join(method.value for method in item.methods())]
                for item in standard_materials().values()
            ],
        )
    )


@catalog.command("sets")
@click.pass_obj
def sets(context: Context) -> None:
    """Every set code the department builds."""
    for code in context.store.catalog.set_codes():
        click.echo(code)


@catalog.command("sheet")
@click.argument("code")
@click.option("--on", "on_day", default=None, help="the day the sheet was in force")
@click.pass_obj
def sheet(context: Context, code: str, on_day: str | None) -> None:
    """The count sheet in force on a day."""
    day = parse_day(on_day) if on_day else context.clock.today()
    history = context.store.catalog.history(code)
    revision = history.at(day)
    click.echo(f"{revision.label()} in force {revision.effective.format()}")
    click.echo(
        table(
            [
                Column("catalog"),
                Column("description"),
                Column("qty", align="right"),
                Column("position"),
            ],
            [
                [line.catalog, line.instrument.description, line.quantity, line.position]
                for line in revision.sheet.lines
            ],
        )
    )
    click.echo()
    click.echo("methods: " + ", ".join(method.value for method in revision.sheet.methods()))
