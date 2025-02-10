"""Quality commands: exceptions, and reading the audit trail.

Raising an exception is deliberately cheap, because an exception nobody raises
is worse than one raised carelessly. Closing one is not: a major or critical
finding will not close without an investigation written into the record.
"""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.quality.audit import Action
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.reporting.render import Column, bullets, pairs, table


@click.group()
def quality() -> None:
    """Exceptions and the audit trail."""


@quality.command("raise")
@click.argument("reference")
@click.argument("description")
@click.option("--category", required=True)
@click.option("--severity", default="minor", show_default=True)
@click.option("--subject", default="", help="the machine, tray or load it is about")
@click.option("--action", "immediate", default="", help="what was done straight away")
@click.pass_obj
def raise_exception(
    context: Context,
    reference: str,
    description: str,
    category: str,
    severity: str,
    subject: str,
    immediate: str,
) -> None:
    """Record something that went wrong."""
    entry = Nonconformance(
        reference=reference,
        category=Category.named(category),
        severity=Severity.named(severity),
        raised_at=context.now(),
        raised_by=context.signed_by(),
        description=description,
        subject=subject,
        immediate_action=immediate,
    )
    context.store.quality.save_exception(entry)
    context.store.quality.record(
        context.now(), entry.raised_by, Action.RECORDED, "exception", entry.reference
    )
    click.echo(f"{entry.summary()}, response due {entry.due_on().isoformat()}")


@quality.command("close")
@click.argument("reference")
@click.option("--investigation", default="", help="required on a major or critical finding")
@click.pass_obj
def close(context: Context, reference: str, investigation: str) -> None:
    """Close an exception."""
    entry = context.store.quality.exception(reference)
    closed = entry.closed(context.now(), context.signed_by(), investigation)
    context.store.quality.save_exception(closed)
    context.store.quality.record(
        context.now(), closed.closed_by, Action.CLOSED, "exception", closed.reference
    )
    click.echo(closed.summary())


@quality.command("open")
@click.pass_obj
def open_exceptions(context: Context) -> None:
    """Everything still open, and whether it is overdue."""
    today = context.clock.today()
    found = context.store.quality.open_exceptions()
    click.echo(
        table(
            [
                Column("reference"),
                Column("severity"),
                Column("category"),
                Column("subject"),
                Column("due"),
                Column("overdue"),
            ],
            [
                [
                    entry.reference,
                    entry.severity.label,
                    entry.category.label,
                    entry.subject,
                    entry.due_on().isoformat(),
                    entry.overdue(today),
                ]
                for entry in found
            ],
        )
    )


@quality.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """One exception in full."""
    entry = context.store.quality.exception(reference)
    click.echo(
        pairs(
            [
                ("reference", entry.reference),
                ("category", entry.category.label),
                ("severity", entry.severity.label),
                ("subject", entry.subject),
                ("raised", entry.raised_at.strftime("%Y-%m-%d %H:%M")),
                ("by", entry.raised_by),
                ("due", entry.due_on().isoformat()),
                ("closed", entry.closed_at.strftime("%Y-%m-%d %H:%M") if entry.closed_at else ""),
            ]
        )
    )
    click.echo()
    click.echo(entry.description)
    if entry.immediate_action:
        click.echo()
        click.echo(f"immediate action: {entry.immediate_action}")
    if entry.investigation:
        click.echo()
        click.echo(f"investigation: {entry.investigation}")


@quality.command("trends")
@click.option("--from", "start", required=True)
@click.option("--to", "end", required=True)
@click.option("--repeat", type=int, default=3, show_default=True)
@click.pass_obj
def trends(context: Context, start: str, end: str, repeat: int) -> None:
    """Counts by category, and the subjects that keep coming back."""
    found = context.store.quality.exceptions_between(parse_day(start), parse_day(end))
    counts: dict[str, int] = {}
    for entry in found:
        counts[entry.category.label] = counts.get(entry.category.label, 0) + 1
    ranked = sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    click.echo(
        table(
            [Column("category"), Column("exceptions", align="right")],
            [[name, total] for name, total in ranked],
        )
    )
    register = context.store.quality.register()
    repeats = register.repeat_subjects(repeat)
    if repeats:
        click.echo()
        click.echo(bullets(f"{subject}: {count} exceptions" for subject, count in repeats))


@quality.command("audit")
@click.option("--kind", default=None, help="load, tray, exception, recall")
@click.option("--subject", default=None)
@click.pass_obj
def audit(context: Context, kind: str | None, subject: str | None) -> None:
    """Read the audit trail, and say whether the chain holds."""
    trail = context.store.quality.audit_trail()
    events = trail.events if kind is None or subject is None else trail.for_subject(kind, subject)
    click.echo(
        table(
            [Column("when"), Column("by"), Column("action"), Column("subject"), Column("detail")],
            [
                [
                    event.at.strftime("%Y-%m-%d %H:%M"),
                    event.by,
                    event.action.label,
                    f"{event.subject_kind} {event.subject}",
                    event.detail,
                ]
                for event in events
            ],
        )
    )
    click.echo()
    click.echo("chain intact" if trail.intact() else "THE CHAIN IS BROKEN")
