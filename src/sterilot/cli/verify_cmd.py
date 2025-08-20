"""Cleaning verification commands.

An A0 value says the load got hot. These say it got clean, which is a different
question and the only one a soiled instrument cares about.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_moment
from sterilot.decon.verification import Verification, VerificationKind
from sterilot.reporting.render import Column, bullets, table


@click.group()
def verify() -> None:
    """Cleaning verification."""


@verify.command("soil")
@click.argument("equipment")
@click.option("--failed", is_flag=True)
@click.option("--lot", default="")
@click.pass_obj
def soil(context: Context, equipment: str, failed: bool, lot: str) -> None:
    """Record a soil test device result."""
    result = Verification(
        kind=VerificationKind.SOIL_DEVICE,
        equipment=equipment,
        at=context.now(),
        by=context.signed_by(),
        visual_pass=not failed,
        lot=lot,
    )
    context.store.verifications.save(result)
    click.echo(result.explain())


@verify.command("residue")
@click.argument("equipment")
@click.argument("kind_name")
@click.option("--value", type=float, required=True)
@click.option("--subject", default="", help="the instrument that was swabbed")
@click.pass_obj
def residue(context: Context, equipment: str, kind_name: str, value: float, subject: str) -> None:
    """Record a measured residue test."""
    result = Verification(
        kind=VerificationKind.named(kind_name),
        equipment=equipment,
        at=context.now(),
        by=context.signed_by(),
        value=value,
        subject=subject,
    )
    context.store.verifications.save(result)
    click.echo(result.explain())
    if not result.passed:
        raise SystemExit(5)


@verify.command("day")
@click.argument("equipment")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def day(context: Context, equipment: str, on_day: str | None) -> None:
    """Everything recorded for a machine on a day."""
    wanted = context.day(on_day)
    found = context.store.verifications.on_day(equipment, wanted)
    click.echo(
        table(
            [Column("when"), Column("test"), Column("result"), Column("subject"), Column("by")],
            [
                [
                    item.at.strftime("%H:%M"),
                    item.kind.label,
                    "pass" if item.passed else "FAIL",
                    item.subject,
                    item.by,
                ]
                for item in found
            ],
        )
    )
    if not context.store.verifications.verified_on(equipment, wanted):
        click.echo()
        click.echo("no passing soil device test that day")


@verify.command("suspect")
@click.argument("equipment")
@click.option("--at", "failed_at", required=True, help="when the test failed")
@click.pass_obj
def suspect(context: Context, equipment: str, failed_at: str) -> None:
    """What a failed verification calls into question."""
    start, end = context.store.verifications.suspect_window(equipment, parse_moment(failed_at))
    click.echo(
        f"{equipment.upper()} is suspect from {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}"
    )
    cycles = [
        cycle
        for cycle in context.store.washers.on_day(equipment, start.date())
        if start <= cycle.started_at <= end
    ]
    if not cycles:
        click.echo("no wash cycles recorded in that window")
        return
    click.echo(bullets(f"cycle {cycle.number} at {cycle.started_at:%H:%M}" for cycle in cycles))
