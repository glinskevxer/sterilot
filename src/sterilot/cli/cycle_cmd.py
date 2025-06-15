"""Sterilizer cycle commands.

A cycle gets into the record one of two ways. Somebody types the numbers off
the tape, or the tape itself is read. The second is preferred and the first has
to exist, because the tape printer fails more often than anything else in the
department and the cycle still has to be recorded.
"""

from __future__ import annotations

from pathlib import Path

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day, parse_moment
from sterilot.ids import LotControlNumber
from sterilot.ingest.printout import parse_printout
from sterilot.ingest.trace_import import load_trace
from sterilot.methods import Method
from sterilot.reporting.render import Column, bullets, pairs, table
from sterilot.sterilizer.cycle import SterilizerCycle
from sterilot.sterilizer.lethality import TERMINAL_FLOOR_MINUTES
from sterilot.sterilizer.lethality import evaluate as evaluate_f0
from sterilot.sterilizer.parameters import CycleMeasurements, CycleSpec
from sterilot.units.duration import Duration
from sterilot.units.pressure import Pressure
from sterilot.units.temperature import Temperature


@click.group()
def cycle() -> None:
    """Sterilizer runs."""


@cycle.command("record")
@click.option("--equipment", required=True)
@click.option("--method", "method_name", required=True)
@click.option("--started", required=True, help="when the cycle started")
@click.option("--temp", "hold", required=True, help="sterilize temperature")
@click.option("--exposure", required=True, help="sterilize time")
@click.option("--dry", default="0", show_default=True)
@click.option("--pressure", default=None, help="chamber pressure, with its unit")
@click.option("--pulses", type=int, default=None)
@click.option("--run", type=int, default=None, help="run number, defaults to the next one")
@click.option("--aborted", default="", help="the reason, if the cycle aborted")
@click.pass_obj
def record(
    context: Context,
    equipment: str,
    method_name: str,
    started: str,
    hold: str,
    exposure: str,
    dry: str,
    pressure: str | None,
    pulses: int | None,
    run: int | None,
    aborted: str,
) -> None:
    """Record a cycle from the numbers on the tape."""
    method = Method.named(method_name)
    started_at = parse_moment(started)
    number = run or context.store.cycles.next_run(equipment, started_at.date())
    measured = CycleMeasurements(
        hold_temperature=Temperature.parse(hold),
        exposure=Duration.parse(exposure, bare_unit="m"),
        dry_time=Duration.parse(dry, bare_unit="m"),
        chamber_pressure=None if pressure is None else _pressure(pressure),
        conditioning_pulses=pulses,
    )
    made = SterilizerCycle(
        lot=LotControlNumber(equipment, started_at.date(), number),
        spec=CycleSpec.standard(method),
        started_at=started_at,
        operator=context.signed_by(),
        measurements=measured,
        aborted=bool(aborted),
        abort_reason=aborted,
    )
    context.store.cycles.save(made)
    click.echo(f"recorded {made.lot.format()}")


@cycle.command("read-tape")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--method", "method_name", default="prevac", show_default=True)
@click.pass_obj
def read_tape(context: Context, path: Path, method_name: str) -> None:
    """Read a printout file and record the cycle it describes."""
    tape = parse_printout(path.read_text(encoding="utf-8"))
    made = SterilizerCycle(
        lot=tape.lot(),
        spec=CycleSpec.standard(Method.named(method_name)),
        started_at=tape.started_at,
        operator=tape.operator,
        measurements=tape.measurements(),
        aborted=tape.aborted,
        abort_reason=tape.abort_reason,
    )
    context.store.cycles.save(made)
    click.echo(f"recorded {made.lot.format()} from {path.name}")


@cycle.command("show")
@click.argument("lot")
@click.pass_obj
def show(context: Context, lot: str) -> None:
    """One cycle and its numbers."""
    found = context.store.cycles.get(lot)
    measured = found.measurements
    click.echo(
        pairs(
            [
                ("lot", found.lot.format()),
                ("chamber", found.equipment),
                ("cycle", found.spec.name),
                ("method", found.method.value),
                ("started", found.started_at.strftime("%Y-%m-%d %H:%M")),
                ("operator", found.operator),
                ("hold", measured.hold_temperature.format()),
                ("exposure", measured.exposure.spelled()),
                ("dry", measured.dry_time.spelled()),
                ("aborted", found.abort_reason or "no"),
            ]
        )
    )


@cycle.command("check")
@click.argument("lot")
@click.pass_obj
def check(context: Context, lot: str) -> None:
    """Judge a cycle against the chamber it ran in.

    This is the cycle on its own. Whether the chamber had a passing air removal
    test that day is a question about the load, and it is asked at release.
    """
    found = context.store.cycles.get(lot)
    unit = context.store.equipment.sterilizer(found.equipment)
    failures = found.failures(unit)
    if not failures:
        click.echo(f"{found.lot.format()} is acceptable")
        return
    click.echo(f"{found.lot.format()} has {len(failures)} problems")
    click.echo(bullets(failures))
    raise SystemExit(5)


@cycle.command("trace")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--floor", type=float, default=TERMINAL_FLOOR_MINUTES, show_default=True)
@click.pass_obj
def trace(context: Context, path: Path, floor: float) -> None:
    """Score a probe trace file for lethality."""
    result = load_trace(path.read_text(encoding="utf-8"))
    click.echo(result.summary())
    if result.trace is None:
        raise SystemExit(2)
    scored = evaluate_f0(result.trace, floor)
    click.echo(
        pairs(
            [
                ("peak", scored.peak.format()),
                ("time above 121.1", scored.time_above_reference.spelled()),
                ("F0", f"{scored.minutes:.1f} min"),
                ("log reductions", f"{scored.log_reductions():.1f}"),
                ("verdict", "clears" if scored.passed else "short"),
            ]
        )
    )
    if result.problems:
        click.echo(bullets(item.describe() for item in result.problems))
    if not scored.passed:
        raise SystemExit(5)


@cycle.command("day")
@click.argument("equipment")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def day(context: Context, equipment: str, on_day: str | None) -> None:
    """Every cycle a chamber ran on a day."""
    wanted = parse_day(on_day) if on_day else context.clock.today()
    found = context.store.cycles.on_day(equipment, wanted)
    click.echo(
        table(
            [
                Column("run", align="right"),
                Column("lot"),
                Column("started"),
                Column("hold"),
                Column("exposure"),
                Column("aborted"),
            ],
            [
                [
                    item.run,
                    item.lot.format(),
                    item.started_at.strftime("%H:%M"),
                    item.measurements.hold_temperature.format(),
                    item.measurements.exposure.spelled(),
                    item.abort_reason or "",
                ]
                for item in found
            ],
        )
    )


def _pressure(text: str) -> Pressure:
    cleaned = text.strip().lower()
    number = float("".join(ch for ch in cleaned if ch.isdigit() or ch in ".-"))
    if "psig" in cleaned:
        return Pressure.from_psig(number)
    if "psia" in cleaned or "psi" in cleaned:
        return Pressure.from_psia(number)
    if "bar" in cleaned:
        return Pressure.from_bar_absolute(number)
    return Pressure.from_kpa_absolute(number)
