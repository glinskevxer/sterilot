"""Writing records out as delimited text.

An inspector asks for the sterilization records for a period and does not want
them one screen at a time. Neither does the hospital's data team, who will
open whatever we give them in a spreadsheet and then ask why the dates sort
wrongly, so the dates go out as ISO text.

Nothing here reads the database. It takes records and returns text, which keeps
it testable and keeps the store out of the reporting layer.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any

from sterilot.errors import ValidationError
from sterilot.load.record import LoadRecord
from sterilot.quality.nonconformance import Nonconformance
from sterilot.sterilizer.cycle import SterilizerCycle

CYCLE_COLUMNS = (
    "lot",
    "sterilizer",
    "run_date",
    "run",
    "cycle",
    "method",
    "started_at",
    "operator",
    "hold_c",
    "exposure_s",
    "dry_s",
    "aborted",
)

LOAD_COLUMNS = (
    "reference",
    "lot",
    "method",
    "status",
    "built_by",
    "built_at",
    "decided_at",
    "decided_by",
    "kind",
    "trays",
    "reasons",
)

EXCEPTION_COLUMNS = (
    "reference",
    "category",
    "severity",
    "subject",
    "raised_at",
    "raised_by",
    "due_on",
    "closed_at",
    "closed_by",
    "description",
)


def write(columns: Sequence[str], rows: Iterable[Sequence[Any]], delimiter: str = ",") -> str:
    """Render rows as delimited text, header first."""
    if not columns:
        raise ValidationError("an export needs columns")
    handle = io.StringIO()
    writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        if len(row) != len(columns):
            raise ValidationError(
                "that row does not match the columns", cells=len(row), columns=len(columns)
            )
        writer.writerow(["" if value is None else value for value in row])
    return handle.getvalue()


def cycles(found: Iterable[SterilizerCycle], delimiter: str = ",") -> str:
    return write(
        CYCLE_COLUMNS,
        [
            [
                cycle.lot.format(),
                cycle.equipment,
                cycle.day.isoformat(),
                cycle.run,
                cycle.spec.name,
                cycle.method.value,
                cycle.started_at.isoformat(timespec="seconds"),
                cycle.operator,
                f"{cycle.measurements.hold_temperature.celsius:.1f}",
                f"{cycle.measurements.exposure.seconds:.0f}",
                f"{cycle.measurements.dry_time.seconds:.0f}",
                "yes" if cycle.aborted else "no",
            ]
            for cycle in found
        ],
        delimiter,
    )


def loads(found: Iterable[LoadRecord], delimiter: str = ",") -> str:
    return write(
        LOAD_COLUMNS,
        [
            [
                record.reference,
                record.lot.format(),
                record.load.method.value,
                record.status.label,
                record.load.built_by,
                record.load.built_at.isoformat(timespec="seconds"),
                None
                if record.decision is None
                else record.decision.at.isoformat(timespec="seconds"),
                None if record.decision is None else record.decision.by,
                None if record.decision is None else record.decision.kind.value,
                " ".join(record.load.assets()),
                "; ".join(() if record.decision is None else record.decision.reasons),
            ]
            for record in found
        ],
        delimiter,
    )


def exceptions(found: Iterable[Nonconformance], delimiter: str = ",") -> str:
    return write(
        EXCEPTION_COLUMNS,
        [
            [
                entry.reference,
                entry.category.value,
                entry.severity.value,
                entry.subject,
                entry.raised_at.isoformat(timespec="seconds"),
                entry.raised_by,
                entry.due_on().isoformat(),
                None if entry.closed_at is None else entry.closed_at.isoformat(timespec="seconds"),
                entry.closed_by,
                entry.description,
            ]
            for entry in found
        ],
        delimiter,
    )
