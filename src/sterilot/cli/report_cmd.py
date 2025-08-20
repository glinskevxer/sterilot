"""Reporting commands.

The daily sheet, and the numbers a supervisor takes to a meeting. Everything
here reads and prints. None of it writes, which is deliberate: a report that
changes the record is not a report.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.quality.metrics import (
    first_pass_yield,
    held_loads,
    rework_rate,
    throughput,
    turnaround_hours,
)
from sterilot.reporting import daily
from sterilot.reporting.render import Column, heading, pairs, table


@click.group()
def report() -> None:
    """Reports, which read and never write."""


@report.command("daily")
@click.option("--on", "on_day", default=None, help="the day to report, defaults to today")
@click.pass_obj
def daily_report(context: Context, on_day: str | None) -> None:
    """The one page daily sheet."""
    day = context.day(on_day)
    click.echo(daily.build(context.store, day, context.settings).render())


@report.command("throughput")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.pass_obj
def throughput_report(context: Context, start: str, end: str) -> None:
    """Loads, trays and chamber units by day."""
    records = context.store.loads.on_days(parse_day(start), parse_day(end))
    totals = throughput(records)
    click.echo(
        table(
            [
                Column("day"),
                Column("loads", align="right"),
                Column("trays", align="right"),
                Column("units", align="right"),
                Column("per load", align="right"),
            ],
            [
                [
                    item.day.isoformat(),
                    item.loads,
                    item.trays,
                    item.units,
                    f"{item.trays_per_load:.1f}",
                ]
                for item in totals
            ],
        )
    )


@report.command("quality")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.pass_obj
def quality_report(context: Context, start: str, end: str) -> None:
    """First pass yield, rework and what is still held."""
    records = context.store.loads.on_days(parse_day(start), parse_day(end))
    if not records:
        click.echo("no loads in that window")
        return
    held = held_loads(records)
    click.echo(heading("Loads", "-"))
    click.echo(
        pairs(
            [
                ("loads", len(records)),
                ("first pass yield", f"{first_pass_yield(records) * 100:.1f} percent"),
                ("rework", f"{rework_rate(records) * 100:.1f} percent"),
                ("held now", len(held)),
            ]
        )
    )
    if held:
        click.echo()
        click.echo(
            table(
                [Column("reference"), Column("waiting on")],
                [
                    [
                        record.reference,
                        "; ".join(record.decision.reasons) if record.decision else "",
                    ]
                    for record in held
                ],
            )
        )


@report.command("turnaround")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.option("--worst", type=int, default=5, show_default=True, help="how many slow trays to list")
@click.pass_obj
def turnaround_report(context: Context, start: str, end: str, worst: int) -> None:
    """How long a tray takes to go round, with the tail shown."""
    runs = context.store.trays.turnarounds(parse_day(start), parse_day(end))
    if not runs:
        click.echo("no completed turnarounds in that window")
        return
    found = turnaround_hours(runs)
    click.echo(heading("Turnaround in hours", "-"))
    click.echo(
        pairs(
            [
                ("trips", found.count),
                ("mean", f"{found.mean:.1f}"),
                ("median", f"{found.median:.1f}"),
                ("ninetieth", f"{found.p90:.1f}"),
                ("worst", f"{found.highest:.1f}"),
            ]
        )
    )
    slowest = sorted(runs, key=lambda run: run.elapsed.seconds, reverse=True)[:worst]
    click.echo()
    click.echo(
        table(
            [Column("tray"), Column("soiled"), Column("sterile"), Column("hours", align="right")],
            [
                [
                    run.asset,
                    run.soiled_at.strftime("%Y-%m-%d %H:%M"),
                    run.sterile_at.strftime("%Y-%m-%d %H:%M"),
                    f"{run.elapsed.hours:.1f}",
                ]
                for run in slowest
            ],
        )
    )


@report.command("machines")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def machines_report(context: Context, on_day: str | None) -> None:
    """Every machine, what it ran and what it owes."""
    day = context.day(on_day)
    rows: list[list[object]] = []
    for unit in context.store.equipment.sterilizers():
        ran = context.store.cycles.on_day(unit.equipment, day)
        logged = context.store.duties.on_day(unit.equipment, day)
        rows.append(
            [
                unit.equipment,
                len(ran),
                sum(1 for item in ran if item.aborted),
                ", ".join(item.duty.label for item in logged if item.passed) or "none",
                unit.refusal_on(day) or "ready",
            ]
        )
    click.echo(
        table(
            [
                Column("chamber"),
                Column("cycles", align="right"),
                Column("aborted", align="right"),
                Column("tests"),
                Column("state"),
            ],
            rows,
        )
    )
