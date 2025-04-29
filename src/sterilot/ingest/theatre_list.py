"""Reading the theatre list.

The list arrives as an export from a system nobody here administers, once a
day, in whatever shape that system feels like. Column names are aliased, rows
that will not parse are reported rather than dropped, and a case already in the
database is updated rather than duplicated, because the list gets re-sent when
somebody moves a case.
"""

from __future__ import annotations

from dataclasses import dataclass

from sterilot.cases.schedule import ScheduledCase
from sterilot.clock import parse_moment
from sterilot.errors import ValidationError
from sterilot.ingest.source import Row, RowProblem, read_delimited

REQUIRED = ("case", "room", "surgeon", "procedure", "start")

ALIASES = {
    "case_id": "case",
    "case_no": "case",
    "case_number": "case",
    "theatre": "room",
    "or": "room",
    "operating_room": "room",
    "consultant": "surgeon",
    "primary_surgeon": "surgeon",
    "operation": "procedure",
    "start_time": "start",
    "scheduled_start": "start",
    "duration": "minutes",
    "duration_min": "minutes",
    "booked_minutes": "minutes",
    "card": "card_reference",
    "preference_card": "card_reference",
}

DEFAULT_MINUTES = 60


@dataclass(frozen=True)
class ListImport:
    """What came out of one theatre export."""

    cases: tuple[ScheduledCase, ...] = ()
    problems: tuple[RowProblem, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.problems

    def rooms(self) -> tuple[str, ...]:
        return tuple(sorted({case.room for case in self.cases}))

    def summary(self) -> str:
        return f"{len(self.cases)} cases read, {len(self.problems)} rows rejected"


def _case(row: Row) -> ScheduledCase:
    minutes = row.get("minutes").strip()
    return ScheduledCase(
        case=row.require("case"),
        room=row.require("room"),
        surgeon=row.require("surgeon"),
        procedure=row.require("procedure"),
        starts_at=parse_moment(row.require("start")),
        minutes=int(minutes) if minutes.isdigit() else DEFAULT_MINUTES,
        card_reference=row.get("card_reference"),
    )


def load_theatre_list(text: str) -> ListImport:
    """Read an export into scheduled cases."""
    result = read_delimited(text, required=REQUIRED, aliases=ALIASES)
    problems = list(result.problems)
    cases: list[ScheduledCase] = []
    seen: set[str] = set()
    for row in result.rows:
        try:
            case = _case(row)
        except ValidationError as exc:
            problems.append(RowProblem(row.number, "will not build a case", exc.message))
            continue
        if case.case in seen:
            problems.append(
                RowProblem(row.number, "is a repeat of a case already in the file", case.case)
            )
            continue
        seen.add(case.case)
        cases.append(case)
    return ListImport(tuple(cases), tuple(problems))
