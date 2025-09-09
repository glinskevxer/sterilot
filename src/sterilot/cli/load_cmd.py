"""Load commands: building a load, and releasing it.

Release is the command that matters and it is deliberately wordy. Every input
the decision uses is named on the command line, because a release that happened
because of a default nobody typed is a release nobody can explain afterwards.
"""

from __future__ import annotations

from datetime import date

import click

from sterilot.assets.lifecycle import Stage, allowed_from
from sterilot.assets.tray import TrayInstance
from sterilot.cli import values
from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.errors import NotFoundError
from sterilot.indicators.chemical import (
    ChemicalIndicator,
    ChemicalResult,
    IndicatorClass,
    Outcome,
    Placement,
)
from sterilot.load.build import Load, LoadItem
from sterilot.load.record import LoadRecord, LoadStatus
from sterilot.load.release import BiologicalOutcome, ReleaseRequest, decide
from sterilot.reporting.render import Column, bullets, pairs, table
from sterilot.units.mass import Mass


@click.group()
def load() -> None:
    """Loads and their release."""


@load.command("build")
@click.argument("reference")
@click.option("--lot", required=True, help="the cycle this load ran in")
@click.option("--tray", "trays", multiple=True, required=True, help="asset tag, repeatable")
@click.option("--implant", "implants", multiple=True, help="asset tags carrying an implant")
@click.option("--textile", "textiles", multiple=True, help="asset tags that are textile packs")
@click.pass_obj
def build(
    context: Context,
    reference: str,
    lot: str,
    trays: tuple[str, ...],
    implants: tuple[str, ...],
    textiles: tuple[str, ...],
) -> None:
    """Build a load against a cycle that has already been recorded."""
    cycle = context.store.cycles.get(lot)
    implant_set = {item.strip().upper() for item in implants}
    textile_set = {item.strip().upper() for item in textiles}
    items = []
    for asset in trays:
        tray = context.store.trays.get(asset)
        if tray.stage is not Stage.ASSEMBLED:
            raise click.ClickException(
                f"{tray.asset} is {tray.stage.label}, a load is built from assembled trays"
            )
        items.append(
            LoadItem(
                asset=tray.asset,
                code=tray.code,
                weight=_sheet_weight(context, tray.code, cycle.day),
                implant=tray.asset in implant_set,
                textile=tray.asset in textile_set,
                shelf=2 if tray.asset in textile_set else 1,
            )
        )
    made = Load.of(reference, cycle.method, items, context.signed_by(), context.now())
    record = LoadRecord(made, cycle)
    context.store.loads.save(record)
    context.store.trays.save_all(
        context.store.trays.get(asset).moved_to(
            Stage.STERILIZING, context.now(), context.signed_by(), made.reference
        )
        for asset in made.assets()
    )
    problems = made.problems(context.store.equipment.sterilizer(cycle.equipment).capacity_units)
    click.echo(f"built {made.label()} on {cycle.lot.format()}")
    if problems:
        click.echo(bullets(problems))


@load.command("release")
@click.argument("reference")
@click.option("--ci-lot", required=True, help="the chemical indicator lot in use")
@click.option("--ci-expires", required=True, help="the expiry printed on the box")
@click.option("--internal", "internal", multiple=True, help="ASSET or ASSET=outcome")
@click.option("--external", "external", multiple=True, help="ASSET or ASSET=outcome")
@click.option("--biological", type=click.Choice(["pass", "fail", "pending"]), default="pending")
@click.option("--wet", is_flag=True, help="the load came out wet")
@click.option("--justify", default="", help="the reason for an early release")
@click.pass_obj
def release(
    context: Context,
    reference: str,
    ci_lot: str,
    ci_expires: str,
    internal: tuple[str, ...],
    external: tuple[str, ...],
    biological: str,
    wet: bool,
    justify: str,
) -> None:
    """Decide whether a load may be released."""
    record = context.store.loads.get(reference)
    cycle = record.cycle
    indicator = ChemicalIndicator(
        IndicatorClass.INTEGRATING,
        ci_lot,
        parse_day(ci_expires),
        frozenset({cycle.method}),
    )
    results: dict[str, list[ChemicalResult]] = {}
    for placement, given in ((Placement.EXTERNAL, external), (Placement.INTERNAL, internal)):
        for entry in given:
            asset, outcome = values.pair(entry)
            strip = Outcome.named(outcome) if outcome else Outcome.PASS
            results.setdefault(asset, []).append(
                ChemicalResult(indicator, placement, strip, context.now(), context.signed_by())
            )
    read: BiologicalOutcome | None = None
    if biological == "pass":
        read = BiologicalOutcome(passed=True, read_at=context.now())
    elif biological == "fail":
        read = BiologicalOutcome(
            passed=False, problems=("the biological indicator grew",), read_at=context.now()
        )
    request = ReleaseRequest(
        load=record.load,
        cycle=cycle,
        sterilizer=context.store.equipment.sterilizer(cycle.equipment),
        at=context.now(),
        by=context.signed_by(),
        chemical={asset: tuple(found) for asset, found in results.items()},
        biological=read,
        wet_pack=wet,
        air_removal_ok=context.store.duties.air_removal_ok(cycle.equipment, cycle.day),
        emergency_justification=justify,
    )
    decision = decide(request, context.settings)
    context.store.loads.save(record.decided(decision))
    if decision.released:
        _to_the_shelf(context, record)
    click.echo(decision.explain())
    if not decision.released:
        raise SystemExit(5)


@load.command("show")
@click.argument("reference")
@click.pass_obj
def show(context: Context, reference: str) -> None:
    """One load, its cycle and what was decided."""
    record = context.store.loads.get(reference)
    click.echo(
        pairs(
            [
                ("reference", record.reference),
                ("lot", record.lot.format()),
                ("method", record.load.method.value),
                ("built by", record.load.built_by),
                ("status", record.status.label),
                ("implant", record.load.carries_implant),
            ]
        )
    )
    click.echo()
    click.echo(
        table(
            [Column("asset"), Column("set"), Column("units", align="right"), Column("implant")],
            [[item.asset, item.code, item.units, item.implant] for item in record.load.items],
        )
    )
    if record.decision is not None and record.decision.reasons:
        click.echo()
        click.echo(bullets(record.decision.reasons))


@load.command("held")
@click.pass_obj
def held(context: Context) -> None:
    """Every load waiting on something."""
    found = context.store.loads.with_status(LoadStatus.HELD)
    click.echo(
        table(
            [Column("reference"), Column("lot"), Column("waiting on")],
            [
                [
                    record.reference,
                    record.lot.format(),
                    "; ".join(record.decision.reasons) if record.decision else "",
                ]
                for record in found
            ],
        )
    )


@load.command("of-tray")
@click.argument("asset")
@click.pass_obj
def of_tray(context: Context, asset: str) -> None:
    """Every load a tray has been in."""
    click.echo(
        table(
            [Column("reference"), Column("lot"), Column("status")],
            [
                [record.reference, record.lot.format(), record.status.label]
                for record in context.store.loads.for_asset(asset)
            ],
        )
    )


def _sheet_weight(context: Context, code: str, day: date) -> Mass | None:
    """What the count sheet says a set weighs, or nothing when we cannot say.

    A weight is only useful if it is complete. A sheet with one unweighed item
    on it would put the whole set under the limit by however much that item
    weighs, which is worse than admitting we do not know.
    """
    try:
        sheet = context.store.catalog.sheet(code, day)
    except NotFoundError:
        return None
    if sheet.weights_missing():
        return None
    return sheet.known_weight()


def _to_the_shelf(context: Context, record: LoadRecord) -> None:
    """Walk every tray in a released load out of the chamber and onto the shelf."""
    moved: list[TrayInstance] = []
    for asset in record.load.assets():
        tray = context.store.trays.get(asset)
        for stage in (Stage.COOLING, Stage.STERILE):
            if tray.stage is stage:
                continue
            if stage in allowed_from(tray.stage):
                tray = tray.moved_to(stage, context.now(), context.signed_by(), record.reference)
        moved.append(tray)
    context.store.trays.save_all(moved)
