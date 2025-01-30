"""Case commands: issuing trays to a room and taking them back.

The return is the interesting half. What comes back decides whether the tray
goes on a shelf or into the washer, and it is the only record that says whether
anything was used on a patient.
"""

from __future__ import annotations

import click

from sterilot.assets.lifecycle import Stage
from sterilot.cases.issue import Disposition, Issue
from sterilot.cli.context import Context
from sterilot.reporting.render import Column, table


@click.group()
def case() -> None:
    """Trays out to theatre and back."""


@case.command("issue")
@click.argument("case_reference")
@click.option("--tray", "trays", multiple=True, required=True, help="asset tag, repeatable")
@click.pass_obj
def issue(context: Context, case_reference: str, trays: tuple[str, ...]) -> None:
    """Send trays to a case."""
    for asset in trays:
        tray = context.store.trays.get(asset)
        record = Issue(tray.asset, case_reference, context.now(), context.signed_by())
        context.store.issues.issue_out(record)
        context.store.trays.save(
            tray.moved_to(Stage.ISSUED, context.now(), context.signed_by(), case_reference)
        )
        click.echo(record.describe())


@case.command("return")
@click.argument("asset")
@click.option(
    "--as",
    "disposition",
    type=click.Choice(["unopened", "opened", "used"]),
    required=True,
    help="what came back",
)
@click.pass_obj
def return_tray(context: Context, asset: str, disposition: str) -> None:
    """Take a tray back from a case."""
    open_issue = context.store.issues.open_for(asset)
    if open_issue is None:
        raise click.ClickException(f"{asset} is not out to a case")
    outcome = Disposition.named(disposition)
    closed = open_issue.returned(context.now(), outcome)
    context.store.issues.save(closed)
    tray = context.store.trays.get(asset)
    stage = Stage.STERILE if outcome is Disposition.UNOPENED else Stage.SOILED
    if outcome is Disposition.USED:
        tray = tray.moved_to(Stage.IN_USE, context.now(), context.signed_by(), closed.case)
    context.store.trays.save(tray.moved_to(stage, context.now(), context.signed_by(), closed.case))
    click.echo(closed.describe())


@case.command("show")
@click.argument("case_reference")
@click.pass_obj
def show(context: Context, case_reference: str) -> None:
    """Every tray that went to a case."""
    found = context.store.issues.for_case(case_reference)
    click.echo(
        table(
            [Column("tray"), Column("out"), Column("back"), Column("as")],
            [
                [
                    item.asset,
                    item.issued_at.strftime("%Y-%m-%d %H:%M"),
                    item.returned_at.strftime("%Y-%m-%d %H:%M") if item.returned_at else "",
                    item.disposition.label,
                ]
                for item in found
            ],
        )
    )


@case.command("out")
@click.pass_obj
def out(context: Context) -> None:
    """Every tray currently out of the department."""
    click.echo(
        table(
            [Column("tray"), Column("case"), Column("since")],
            [
                [item.asset, item.case, item.issued_at.strftime("%Y-%m-%d %H:%M")]
                for item in context.store.issues.open_issues()
            ],
        )
    )


@case.command("where")
@click.argument("asset")
@click.pass_obj
def where(context: Context, asset: str) -> None:
    """Where one tray is, as a recall would read it."""
    place, detail = context.store.issues.whereabouts(asset)
    click.echo(f"{place.label} {detail}".strip())
    click.echo(place.action)
