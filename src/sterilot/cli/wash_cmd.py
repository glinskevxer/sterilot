"""Wash commands: programs, cycles and the machine export.

The import is the one that gets used. Somebody drops the day's export on the
share and this reads it, which is the difference between a department that
records its wash cycles and one that means to.
"""

from __future__ import annotations

from pathlib import Path

import click

from sterilot.cli import values
from sterilot.cli.context import Context
from sterilot.clock import parse_day, parse_moment
from sterilot.decon.a0 import ROUTINE_FLOOR, evaluate
from sterilot.decon.cycle import Phase, PhaseRecord, WasherCycle
from sterilot.ingest.washer_export import load_washer_cycles
from sterilot.reporting.render import Column, bullets, pairs, table
from sterilot.trace import Trace
from sterilot.units.duration import Duration
from sterilot.units.temperature import Temperature


@click.group()
def wash() -> None:
    """Washer programs and the cycles run on them."""


@wash.command("programs")
@click.pass_obj
def programs(context: Context) -> None:
    """Every wash program the department has defined."""
    found = context.store.washers.programs()
    if not found:
        click.echo("no programs defined")
        return
    click.echo(
        table(
            [Column("name"), Column("class"), Column("phases"), Column("A0 floor", align="right")],
            [
                [
                    program.name,
                    program.washer_class.label,
                    ", ".join(spec.phase.label for spec in program.phases),
                    program.a0_floor if program.a0_floor is not None else "",
                ]
                for program in found.values()
            ],
        )
    )


@wash.command("seed-standard")
@click.pass_obj
def seed_standard(context: Context) -> None:
    """Create the department's standard instrument program if it is missing."""
    program = context.store.washers.standard_program()
    click.echo(f"{program.name} has {len(program.phases)} phases")


@wash.command("record")
@click.option("--equipment", required=True)
@click.option("--program", "program_name", required=True)
@click.option("--number", type=int, required=True)
@click.option("--started", required=True)
@click.option(
    "--phase",
    "phase_values",
    multiple=True,
    required=True,
    help="PHASE=SECONDS[:PEAK_C], repeatable",
)
@click.option("--aborted", is_flag=True)
@click.pass_obj
def record(
    context: Context,
    equipment: str,
    program_name: str,
    number: int,
    started: str,
    phase_values: tuple[str, ...],
    aborted: bool,
) -> None:
    """Record one wash cycle."""
    program = context.store.washers.program(program_name)
    records = tuple(_phase(value) for value in phase_values)
    cycle = WasherCycle(
        equipment=equipment,
        program=program,
        number=number,
        started_at=parse_moment(started),
        operator=context.signed_by(),
        phases=records,
        aborted=aborted,
    )
    context.store.washers.save_cycle(cycle)
    click.echo(f"recorded {cycle.equipment} cycle {cycle.number}")


@wash.command("check")
@click.option("--equipment", required=True)
@click.option("--number", type=int, required=True)
@click.option("--started", required=True)
@click.pass_obj
def check(context: Context, equipment: str, number: int, started: str) -> None:
    """Judge a wash cycle against its program and its machine."""
    cycle = context.store.washers.cycle(equipment, parse_moment(started), number)
    washer = context.store.equipment.washer(equipment)
    failures = cycle.failures(washer)
    if not failures:
        click.echo(f"{cycle.equipment} cycle {cycle.number} is acceptable")
        return
    click.echo(f"{cycle.equipment} cycle {cycle.number} has {len(failures)} problems")
    click.echo(bullets(failures))
    raise SystemExit(5)


@wash.command("day")
@click.argument("equipment")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def day(context: Context, equipment: str, on_day: str | None) -> None:
    """Every wash cycle a machine ran on a day."""
    wanted = parse_day(on_day) if on_day else context.clock.today()
    found = context.store.washers.on_day(equipment, wanted)
    click.echo(
        table(
            [
                Column("cycle", align="right"),
                Column("started"),
                Column("program"),
                Column("phases", align="right"),
                Column("aborted"),
            ],
            [
                [
                    item.number,
                    item.started_at.strftime("%H:%M"),
                    item.program.name,
                    len(item.phases),
                    item.aborted,
                ]
                for item in found
            ],
        )
    )


@wash.command("import")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_obj
def import_export(context: Context, path: Path) -> None:
    """Read a washer export file and record every cycle in it."""
    programs = context.store.washers.programs()
    if not programs:
        raise click.ClickException("no wash programs are defined yet")
    result = load_washer_cycles(path.read_text(encoding="utf-8"), programs)
    for cycle in result.cycles:
        context.store.washers.save_cycle(cycle)
    click.echo(result.summary())
    if result.problems:
        click.echo(bullets(item.describe() for item in result.problems))
        raise SystemExit(2)


@wash.command("a0")
@click.option("--celsius", type=float, required=True, help="the temperature held")
@click.option("--minutes", type=float, required=True)
@click.option("--floor", type=float, default=ROUTINE_FLOOR, show_default=True)
@click.pass_obj
def a0(context: Context, celsius: float, minutes: float, floor: float) -> None:
    """Score a flat hold against an A0 floor, for working out a program."""
    trace = Trace.flat(context.now(), celsius, minutes * 60.0, step=30.0)
    result = evaluate(trace, floor)
    click.echo(
        pairs(
            [
                ("A0", f"{result.value:.0f}"),
                ("floor", f"{result.floor:.0f}"),
                ("peak", result.peak.format()),
                ("verdict", "clears" if result.passed else "short"),
            ]
        )
    )


def _phase(entry: str) -> PhaseRecord:
    name, seconds, peak = values.triple(entry)
    return PhaseRecord(
        Phase.named(name),
        Duration.parse(seconds or "0", bare_unit="s"),
        Temperature.parse(peak) if peak else None,
    )
