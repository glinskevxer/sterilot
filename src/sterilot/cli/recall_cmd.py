"""Recall commands.

Working out the scope of a failed test, and turning it into the list of things
somebody has to do. Raising a notice also marks every load in scope as
recalled, because a recall that lives only on a printout is a recall the next
person to pick a tray knows nothing about.
"""

from __future__ import annotations

from datetime import date, timedelta

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_moment
from sterilot.load.record import LoadRegister
from sterilot.quality.audit import Action
from sterilot.quality.log import Duty
from sterilot.recall.notice import notice_for
from sterilot.recall.scope import QualificationEvent, RecallScope, Trigger, scope_for
from sterilot.reporting.render import Column, table

EPOCH = date(2000, 1, 1)
"""As far back as the duty log is ever read, which is before this system."""


def _register(context: Context, equipment: str) -> LoadRegister:
    return LoadRegister.of(context.store.loads.on_equipment(equipment))


def _events(context: Context, equipment: str, kind: Trigger) -> tuple[QualificationEvent, ...]:
    duty = Duty.AIR_REMOVAL if kind is Trigger.AIR_REMOVAL else Duty.BIOLOGICAL
    horizon = context.clock.today() + timedelta(days=1)
    found: list[QualificationEvent] = []
    for entry in context.store.duties.between(EPOCH, horizon).entries:
        if entry.equipment != equipment.upper() or entry.duty is not duty:
            continue
        found.append(
            QualificationEvent(
                entry.equipment,
                kind,
                parse_moment(f"{entry.day.isoformat()} 07:00"),
                entry.passed,
            )
        )
    return tuple(found)


def _scope(context: Context, equipment: str, kind: str, at: str) -> RecallScope:
    trigger = Trigger.named(kind)
    failure = QualificationEvent(equipment, trigger, parse_moment(at), False)
    return scope_for(_register(context, equipment), _events(context, equipment, trigger), failure)


@click.group()
def recall() -> None:
    """What a failed test calls into question."""


@recall.command("scope")
@click.option("--equipment", required=True)
@click.option("--kind", default="biological", show_default=True)
@click.option("--at", "failed_at", required=True, help="when the test failed")
@click.pass_obj
def scope(context: Context, equipment: str, kind: str, failed_at: str) -> None:
    """Which loads a failed test reaches, without changing anything."""
    found = _scope(context, equipment, kind, failed_at)
    click.echo(found.summary())
    click.echo()
    click.echo(
        table(
            [Column("load"), Column("lot"), Column("status"), Column("trays")],
            [
                [
                    record.reference,
                    record.lot.format(),
                    record.status.label,
                    ", ".join(record.load.assets()),
                ]
                for record in found.loads
            ],
        )
    )


@recall.command("raise")
@click.argument("reference")
@click.option("--equipment", required=True)
@click.option("--kind", default="biological", show_default=True)
@click.option("--at", "failed_at", required=True)
@click.option("--dry-run", is_flag=True, help="print the notice without marking anything")
@click.pass_obj
def raise_recall(
    context: Context, reference: str, equipment: str, kind: str, failed_at: str, dry_run: bool
) -> None:
    """Raise a recall notice and mark every load in scope."""
    found = _scope(context, equipment, kind, failed_at)
    locations = context.store.issues.locations(found.assets())
    notice = notice_for(reference, found, locations, context.now(), context.signed_by())
    click.echo(notice.render())
    if dry_run:
        click.echo()
        click.echo("dry run, nothing was marked")
        return
    for record in found.loads:
        if record.recalled_at is None:
            context.store.loads.save(
                record.recalled(context.now(), f"{notice.reference} {found.kind.label} failure")
            )
    context.store.quality.record(
        context.now(),
        context.signed_by(),
        Action.RECALLED,
        "recall",
        notice.reference,
        f"{found.load_count} loads on {equipment.upper()}",
    )
    click.echo()
    click.echo(f"marked {found.load_count} loads recalled")


@recall.command("trays")
@click.option("--equipment", required=True)
@click.option("--kind", default="biological", show_default=True)
@click.option("--at", "failed_at", required=True)
@click.pass_obj
def trays(context: Context, equipment: str, kind: str, failed_at: str) -> None:
    """Where every tray in scope is now."""
    found = _scope(context, equipment, kind, failed_at)
    locations = context.store.issues.locations(found.assets())
    click.echo(
        table(
            [Column("tray"), Column("where"), Column("detail"), Column("action")],
            [
                [asset, where.label, detail, where.action]
                for asset, (where, detail) in sorted(locations.items())
            ],
        )
    )
