"""Loaner commands.

Booking a vendor set in, counting it, and the morning list of the ones that
will not be ready. The lead time comes from the department settings rather than
from the option, so a hospital that runs a different window changes it once.
"""

from __future__ import annotations

import click

from sterilot.assets.loaner import LoanerSet
from sterilot.cli.context import Context
from sterilot.clock import parse_day, parse_moment
from sterilot.reporting.render import Column, bullets, pairs, table


@click.group()
def loaner() -> None:
    """Vendor sets, while they are here."""


@loaner.command("book")
@click.argument("reference")
@click.option("--vendor", required=True)
@click.option("--set-name", required=True)
@click.option("--case", required=True)
@click.option("--case-start", required=True)
@click.option("--expected", required=True, help="when the vendor says it will arrive")
@click.pass_obj
def book(
    context: Context,
    reference: str,
    vendor: str,
    set_name: str,
    case: str,
    case_start: str,
    expected: str,
) -> None:
    """Book a loaner in against a case."""
    made = LoanerSet(
        reference=reference,
        vendor=vendor,
        set_name=set_name,
        case=case,
        case_start=parse_moment(case_start),
        expected_at=parse_moment(expected),
    )
    context.store.loaners.save(made)
    deadline = made.deadline(context.settings.loaner_lead_hours)
    click.echo(f"booked {made.label()}, due by {deadline:%Y-%m-%d %H:%M}")


@loaner.command("receive")
@click.argument("reference")
@click.pass_obj
def receive(context: Context, reference: str) -> None:
    """Record a loaner arriving."""
    found = context.store.loaners.get(reference)
    updated = LoanerSet(
        reference=found.reference,
        vendor=found.vendor,
        set_name=found.set_name,
        case=found.case,
        case_start=found.case_start,
        expected_at=found.expected_at,
        received_at=context.now(),
    )
    context.store.loaners.save(updated)
    lead = updated.lead_time()
    hours = f"{lead.hours:.1f}" if lead is not None else "0"
    click.echo(f"{updated.reference} received, {hours} hours before the case")


@loaner.command("count")
@click.argument("reference")
@click.option("--pieces", type=int, required=True)
@click.option("--rep-present/--no-rep", default=True, show_default=True)
@click.pass_obj
def count(context: Context, reference: str, pieces: int, rep_present: bool) -> None:
    """Count a loaner in, with the vendor representative present."""
    found = context.store.loaners.get(reference)
    if found.received_at is None:
        raise click.ClickException(f"{found.reference} has not arrived")
    updated = _with(
        found, counted_at=context.now(), piece_count=pieces, rep_present_at_count=rep_present
    )
    context.store.loaners.save(updated)
    click.echo(f"{updated.reference} counted, {pieces} pieces")


@loaner.command("reprocessed")
@click.argument("reference")
@click.pass_obj
def reprocessed(context: Context, reference: str) -> None:
    """Record that we have run the set through ourselves."""
    found = context.store.loaners.get(reference)
    updated = _with(found, reprocessed_at=context.now())
    context.store.loaners.save(updated)
    problems = updated.problems(context.settings.loaner_lead_hours)
    click.echo(f"{updated.reference} reprocessed")
    if problems:
        click.echo(bullets(problems))


@loaner.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """One loaner and whether it is fit to go out."""
    found = context.store.loaners.get(reference)
    lead = found.lead_time()
    click.echo(
        pairs(
            [
                ("reference", found.reference),
                ("vendor", found.vendor),
                ("set", found.set_name),
                ("case", found.case),
                ("case start", found.case_start.strftime("%Y-%m-%d %H:%M")),
                ("stage", found.stage.label),
                ("lead time", f"{lead.hours:.1f} hours" if lead is not None else "not arrived"),
                ("ready", found.ready_for_case(context.settings.loaner_lead_hours)),
            ]
        )
    )
    problems = found.problems(context.settings.loaner_lead_hours)
    if problems:
        click.echo()
        click.echo(bullets(problems))


@loaner.command("due")
@click.option("--on", "on_day", default=None)
@click.pass_obj
def due(context: Context, on_day: str | None) -> None:
    """The loaners for a day's cases that are not ready."""
    day = parse_day(on_day) if on_day else context.clock.today()
    found = context.store.loaners.not_ready(day, context.settings.loaner_lead_hours)
    if not found:
        click.echo("every loaner for that day is ready")
        return
    click.echo(
        table(
            [Column("reference"), Column("case"), Column("stage"), Column("problems")],
            [
                [item.reference, item.case, item.stage.label, "; ".join(problems)]
                for item, problems in found
            ],
        )
    )


@loaner.command("outstanding")
@click.pass_obj
def outstanding(context: Context) -> None:
    """Every vendor set still in the building."""
    click.echo(
        table(
            [Column("reference"), Column("vendor"), Column("case"), Column("stage")],
            [
                [item.reference, item.vendor, item.case, item.stage.label]
                for item in context.store.loaners.outstanding()
            ],
        )
    )


def _with(found: LoanerSet, **changes: object) -> LoanerSet:
    values: dict[str, object] = {
        "reference": found.reference,
        "vendor": found.vendor,
        "set_name": found.set_name,
        "case": found.case,
        "case_start": found.case_start,
        "expected_at": found.expected_at,
        "received_at": found.received_at,
        "counted_at": found.counted_at,
        "reprocessed_at": found.reprocessed_at,
        "released_at": found.released_at,
        "decontaminated_at": found.decontaminated_at,
        "returned_at": found.returned_at,
        "piece_count": found.piece_count,
        "rep_present_at_count": found.rep_present_at_count,
    }
    values.update(changes)
    return LoanerSet(**values)  # type: ignore[arg-type]
