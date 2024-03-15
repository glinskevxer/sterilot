from __future__ import annotations

from datetime import date

import pytest

from sterilot.catalog.instrument import Instrument
from sterilot.catalog.material import material_named
from sterilot.catalog.revision import Revision, RevisionHistory, history_for
from sterilot.catalog.tray import CountLine, CountSheet
from sterilot.errors import NotFoundError, ValidationError
from sterilot.interval import DateRange


def item(catalog: str) -> Instrument:
    return Instrument(catalog, "forceps", "V Mueller", material_named("SS"))


def sheet(quantities: dict[str, int], code: str = "ORT-MAJOR") -> CountSheet:
    lines = [CountLine(item(catalog), quantity=count) for catalog, count in quantities.items()]
    return CountSheet.of(code, "orthopaedic major set", lines)


def test_a_history_starts_with_revision_one() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 1, 1))
    assert history.current.number == 1
    assert history.current.current
    assert history.current.effective.start == date(2024, 1, 1)


def test_a_revision_number_starts_at_one() -> None:
    with pytest.raises(ValidationError):
        Revision(0, sheet({"SU-1": 1}), DateRange.starting(date(2024, 1, 1)))


def test_revising_closes_the_previous_revision_the_same_day() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 1, 1))
    history = history.revised(sheet({"SU-1": 4}), date(2024, 6, 1), note="surgeon request")
    first = history.numbered(1)
    assert first.effective.end == date(2024, 6, 1)
    assert first.effective.last_day == date(2024, 5, 31)
    assert history.current.number == 2
    assert history.current.note == "surgeon request"


def test_a_tray_assembled_in_march_is_judged_against_the_march_sheet() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 1, 1))
    history = history.revised(sheet({"SU-1": 4}), date(2024, 6, 1))
    assert history.at(date(2024, 3, 15)).sheet.line_for("SU-1").quantity == 2
    assert history.at(date(2024, 6, 1)).sheet.line_for("SU-1").quantity == 4


def test_a_day_before_the_first_revision_has_no_sheet() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 1, 1))
    with pytest.raises(NotFoundError):
        history.at(date(2023, 12, 31))


def test_a_revision_cannot_start_before_the_one_it_replaces() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 6, 1))
    with pytest.raises(ValidationError):
        history.revised(sheet({"SU-1": 4}), date(2024, 1, 1))


def test_a_revision_of_a_different_set_is_refused() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 1, 1))
    with pytest.raises(ValidationError):
        history.revised(sheet({"SU-1": 2}, "GEN-MINOR"), date(2024, 6, 1))


def test_numbered_refuses_a_revision_that_does_not_exist() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2}), date(2024, 1, 1))
    with pytest.raises(NotFoundError):
        history.numbered(7)


def test_changes_name_what_moved() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2, "SU-2": 1}), date(2024, 1, 1))
    history = history.revised(sheet({"SU-1": 4, "SU-3": 1}), date(2024, 6, 1))
    changes = history.changes(1, 2)
    assert [change.describe() for change in changes] == [
        "SU-1 changed from 2 to 4",
        "SU-2 removed, was 1",
        "SU-3 added, 1",
    ]


def test_an_unchanged_line_does_not_appear_in_the_diff() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 2, "SU-2": 1}), date(2024, 1, 1))
    history = history.revised(sheet({"SU-1": 2, "SU-2": 3}), date(2024, 6, 1))
    assert [change.catalog for change in history.changes(1, 2)] == ["SU-2"]


def test_a_history_needs_a_revision() -> None:
    with pytest.raises(ValidationError):
        RevisionHistory("ORT-MAJOR", ())


def test_three_revisions_leave_exactly_one_open() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 1}), date(2024, 1, 1))
    history = history.revised(sheet({"SU-1": 2}), date(2024, 4, 1))
    history = history.revised(sheet({"SU-1": 3}), date(2024, 9, 1))
    assert [revision.number for revision in history.revisions] == [1, 2, 3]
    assert sum(1 for revision in history.revisions if revision.current) == 1
    assert history.at(date(2024, 5, 1)).number == 2


def test_revision_label() -> None:
    history = RevisionHistory.started(sheet({"SU-1": 1}), date(2024, 1, 1))
    assert str(history.current) == "ORT-MAJOR rev 1"


def test_history_lookup_by_code() -> None:
    first = RevisionHistory.started(sheet({"SU-1": 1}, "ORT-MAJOR"), date(2024, 1, 1))
    second = RevisionHistory.started(sheet({"SU-2": 1}, "GEN-MINOR"), date(2024, 1, 1))
    assert history_for([first, second], "gen minor").code == "GEN-MINOR"
    with pytest.raises(NotFoundError):
        history_for([first, second], "NOPE")
