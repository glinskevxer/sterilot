"""Staff commands: the roster, certifications and competencies."""

from __future__ import annotations

import click

from sterilot.cli.context import Context
from sterilot.clock import parse_day
from sterilot.interval import DateRange
from sterilot.reporting.render import Column, pairs, table
from sterilot.staff.competency import Competency, Task
from sterilot.staff.tech import Certification, Role, Technician


@click.group()
def staff() -> None:
    """Who works here and what they may do."""


@staff.command("add")
@click.argument("badge")
@click.argument("name")
@click.option("--role", default="technician", show_default=True)
@click.pass_obj
def add(context: Context, badge: str, name: str, role: str) -> None:
    """Put somebody on the roster."""
    person = Technician(badge, name, Role.named(role))
    context.store.staff.save(person)
    click.echo(f"added {person.label()} as {person.role.label}")


@staff.command("certify")
@click.argument("badge")
@click.option("--body", required=True, help="the certifying body")
@click.option("--number", required=True)
@click.option("--from", "start", required=True)
@click.option("--to", "end", default=None, help="leave off for one that does not expire")
@click.pass_obj
def certify(
    context: Context, badge: str, body: str, number: str, start: str, end: str | None
) -> None:
    """Record a certification."""
    person = context.store.staff.get(badge)
    window = DateRange(parse_day(start), parse_day(end) if end else None)
    grown = person.with_certification(Certification(body, number, window))
    context.store.staff.save(grown)
    click.echo(f"{grown.badge} holds {len(grown.certifications)} certifications")


@staff.command("assess")
@click.argument("badge")
@click.argument("task_name")
@click.option("--on", "assessed_on", default=None)
@click.option("--observations", type=int, default=1, show_default=True)
@click.pass_obj
def assess(
    context: Context, badge: str, task_name: str, assessed_on: str | None, observations: int
) -> None:
    """Sign somebody off on a task."""
    day = parse_day(assessed_on) if assessed_on else context.clock.today()
    entry = Competency(
        badge=badge,
        task=Task.named(task_name),
        assessed_on=day,
        assessor=context.signed_by(),
        observations=observations,
    )
    context.store.staff.save_competency(entry)
    click.echo(entry.describe())


@staff.command("show")
@click.argument("badge")
@click.pass_obj
def show(context: Context, badge: str) -> None:
    """One person, their certifications and their competencies."""
    day = context.clock.today()
    person = context.store.staff.get(badge)
    click.echo(
        pairs(
            [
                ("badge", person.badge),
                ("name", person.name),
                ("role", person.role.label),
                ("certified", person.certified_on(day)),
                ("may release", person.may_release(day)),
            ]
        )
    )
    click.echo()
    click.echo(
        table(
            [Column("certification"), Column("window")],
            [[f"{item.body} {item.number}", item.held.format()] for item in person.certifications],
        )
    )
    file = context.store.staff.competencies(badge)
    click.echo()
    click.echo(
        table(
            [Column("task"), Column("assessed"), Column("by"), Column("current")],
            [
                [item.task.label, item.assessed_on.isoformat(), item.assessor, item.current_on(day)]
                for item in file.for_badge(badge)
            ],
        )
    )


@staff.command("roster")
@click.pass_obj
def roster(context: Context) -> None:
    """Everyone, and who can sign a release."""
    day = context.clock.today()
    people = context.store.staff.roster()
    click.echo(
        table(
            [Column("badge"), Column("name"), Column("role"), Column("release")],
            [
                [
                    person.badge,
                    person.name,
                    person.role.label,
                    context.store.staff.may_release(person.badge, day) or "yes",
                ]
                for person in people.people
            ],
        )
    )


@staff.command("due")
@click.option("--within", type=int, default=60, show_default=True, help="days")
@click.pass_obj
def due(context: Context, within: int) -> None:
    """Competencies about to lapse."""
    day = context.clock.today()
    found = context.store.staff.competencies().due_within(day, within)
    click.echo(
        table(
            [Column("badge"), Column("task"), Column("days left", align="right")],
            [[item.badge, item.task.label, item.days_left(day)] for item in found],
        )
    )
