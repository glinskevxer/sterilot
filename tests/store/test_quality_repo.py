from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ConflictError, NotFoundError
from sterilot.quality.audit import GENESIS, Action, AuditEvent
from sterilot.quality.nonconformance import Category, Nonconformance, Severity
from sterilot.store.db import Database
from sterilot.store.migrations import migrate
from sterilot.store.quality_repo import QualityStore

RAISED = datetime(2024, 12, 10, 9, 0)


def store() -> QualityStore:
    db = Database.in_memory()
    migrate(db)
    return QualityStore(db)


def entry(reference: str = "NC-4401", subject: str = "AC-1", **changes: object) -> Nonconformance:
    values: dict[str, object] = {
        "reference": reference,
        "category": Category.STERILIZATION,
        "severity": Severity.MINOR,
        "raised_at": RAISED,
        "raised_by": "T-4471",
        "description": "wet pack on unloading",
        "subject": subject,
    }
    values.update(changes)
    return Nonconformance(**values)  # type: ignore[arg-type]


def test_an_exception_round_trips() -> None:
    quality = store()
    quality.save_exception(entry(immediate_action="load reprocessed"))
    found = quality.exception("nc 4401")
    assert found.description == "wet pack on unloading"
    assert found.immediate_action == "load reprocessed"
    assert found.open
    quality.db.close()


def test_a_closed_exception_keeps_its_investigation() -> None:
    quality = store()
    closed = entry(severity=Severity.MAJOR).closed(
        datetime(2024, 12, 12, 9, 0), "T-9002", "steam trap replaced"
    )
    quality.save_exception(closed)
    found = quality.exception("NC-4401")
    assert not found.open
    assert found.investigation == "steam trap replaced"
    assert found.closed_by == "T-9002"
    quality.db.close()


def test_an_unknown_reference_is_refused() -> None:
    quality = store()
    with pytest.raises(NotFoundError):
        quality.exception("NC-9999")
    quality.db.close()


def test_open_and_subject_filters() -> None:
    quality = store()
    quality.save_exception(entry("NC-1"))
    quality.save_exception(
        entry("NC-2", subject="AC-2").closed(datetime(2024, 12, 11, 9, 0), "T-9002")
    )
    assert [item.reference for item in quality.open_exceptions()] == ["NC-1"]
    assert [item.reference for item in quality.exceptions_about("ac-1")] == ["NC-1"]
    quality.db.close()


def test_a_window_of_days_is_half_open() -> None:
    quality = store()
    quality.save_exception(entry("NC-1"))
    quality.save_exception(entry("NC-2", raised_at=datetime(2024, 12, 12, 9, 0)))
    found = quality.exceptions_between(date(2024, 12, 10), date(2024, 12, 12))
    assert [item.reference for item in found] == ["NC-1"]
    quality.db.close()


def test_the_whole_register_comes_back() -> None:
    quality = store()
    quality.save_exception(entry("NC-1"))
    quality.save_exception(entry("NC-2"))
    register = quality.register()
    assert len(register.entries) == 2
    assert register.by_category() == {Category.STERILIZATION: 2}
    quality.db.close()


def test_an_empty_audit_trail_starts_at_genesis() -> None:
    quality = store()
    assert quality.audit_head() == GENESIS
    assert quality.audit_trail().intact()
    quality.db.close()


def test_audit_entries_chain_as_they_are_recorded() -> None:
    quality = store()
    first = quality.record(RAISED, "T-4471", Action.RECORDED, "load", "LD-1")
    second = quality.record(
        datetime(2024, 12, 10, 10, 0), "T-9002", Action.RELEASED, "load", "LD-1"
    )
    assert second.previous == first.digest()
    trail = quality.audit_trail()
    assert trail.intact()
    assert len(trail.events) == 2
    quality.db.close()


def test_an_entry_that_does_not_chain_is_refused() -> None:
    quality = store()
    quality.record(RAISED, "T-4471", Action.RECORDED, "load", "LD-1")
    stray = AuditEvent(
        datetime(2024, 12, 10, 11, 0), "T-4471", Action.RELEASED, "load", "LD-1", "", GENESIS
    )
    with pytest.raises(ConflictError):
        quality.append_audit(stray)
    quality.db.close()


def test_audit_entries_are_filtered_by_subject() -> None:
    quality = store()
    quality.record(RAISED, "T-4471", Action.RECORDED, "load", "LD-1")
    quality.record(datetime(2024, 12, 10, 10, 0), "T-4471", Action.RECORDED, "tray", "ORT-0114")
    assert len(quality.audit_for("load", "LD-1")) == 1
    assert len(quality.audit_for("tray", "ORT-0114")) == 1
    assert quality.audit_for("load", "LD-9") == ()
    quality.db.close()


def test_the_trail_survives_a_reload() -> None:
    quality = store()
    quality.record(RAISED, "T-4471", Action.RECORDED, "load", "LD-1")
    quality.record(datetime(2024, 12, 10, 10, 0), "T-4471", Action.HELD, "load", "LD-1")
    head = quality.audit_head()
    again = QualityStore(quality.db)
    assert again.audit_head() == head
    assert again.audit_trail().intact()
    quality.db.close()
