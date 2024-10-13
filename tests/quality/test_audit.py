from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ConflictError, ValidationError
from sterilot.quality.audit import GENESIS, Action, AuditEvent, AuditTrail, rebuild

AT = datetime(2024, 10, 10, 9, 0)


def trail() -> AuditTrail:
    made = AuditTrail()
    made = made.record(AT, "t 4471", Action.RECORDED, "load", "LD-4412")
    made = made.record(datetime(2024, 10, 10, 10, 0), "T-9002", Action.RELEASED, "load", "LD-4412")
    return made


def test_action_lookup_and_which_need_a_reason() -> None:
    assert Action.named("overridden") is Action.OVERRIDDEN
    assert Action.AMENDED.needs_reason
    assert not Action.RECORDED.needs_reason
    with pytest.raises(ValidationError):
        Action.named("fiddled")


def test_an_entry_names_its_subject() -> None:
    with pytest.raises(ValidationError):
        AuditEvent(AT, "T-4471", Action.RECORDED, " ", "LD-1")
    with pytest.raises(ValidationError):
        AuditEvent(AT, "T-4471", Action.RECORDED, "load", "")


def test_an_action_that_needs_a_reason_gets_one() -> None:
    with pytest.raises(ValidationError):
        AuditEvent(AT, "T-4471", Action.OVERRIDDEN, "load", "LD-1")
    assert AuditEvent(AT, "T-4471", Action.OVERRIDDEN, "load", "LD-1", "trauma case").detail


def test_an_empty_trail_starts_at_genesis() -> None:
    assert AuditTrail().head == GENESIS
    assert AuditTrail().intact()


def test_entries_chain_to_the_one_before() -> None:
    made = trail()
    assert made.events[0].previous == GENESIS
    assert made.events[1].previous == made.events[0].digest()
    assert made.head == made.events[1].digest()
    assert made.intact()


def test_an_entry_cannot_predate_the_one_before_it() -> None:
    with pytest.raises(ConflictError):
        trail().record(datetime(2024, 10, 9, 9, 0), "T-4471", Action.HELD, "load", "LD-4412")


def test_altering_an_entry_breaks_the_chain() -> None:
    made = trail()
    tampered = AuditEvent(
        made.events[0].at,
        made.events[0].by,
        Action.RELEASED,
        made.events[0].subject_kind,
        made.events[0].subject,
        made.events[0].detail,
        made.events[0].previous,
    )
    broken = AuditTrail((tampered, made.events[1]))
    assert not broken.intact()
    assert broken.broken_at() == 1


def test_removing_an_entry_breaks_the_chain() -> None:
    made = trail()
    broken = AuditTrail((made.events[1],))
    assert broken.broken_at() == 0


def test_the_digest_depends_on_every_field() -> None:
    first = AuditEvent(AT, "T-4471", Action.RECORDED, "load", "LD-1")
    second = AuditEvent(AT, "T-4471", Action.RECORDED, "load", "LD-2")
    assert first.digest() != second.digest()
    assert len(first.digest()) == 64


def test_filters_by_subject_badge_and_action() -> None:
    made = trail().record(
        datetime(2024, 10, 11, 9, 0), "T-9002", Action.RECALLED, "load", "LD-9999", "positive BI"
    )
    assert len(made.for_subject("load", "LD-4412")) == 2
    assert len(made.by_badge("t 9002")) == 2
    assert len(made.of_action(Action.RECALLED)) == 1


def test_the_window_is_half_open() -> None:
    made = trail()
    found = made.between(AT, datetime(2024, 10, 10, 10, 0))
    assert len(found) == 1
    with pytest.raises(ValidationError):
        made.between(datetime(2024, 10, 11), datetime(2024, 10, 10))


def test_rendering_reads_like_a_log() -> None:
    lines = trail().render().splitlines()
    assert lines[0] == "2024-10-10 09:00 T-4471 recorded load LD-4412"
    assert lines[1].endswith("released load LD-4412")


def test_a_detail_lands_in_the_description() -> None:
    event = AuditEvent(AT, "T-4471", Action.AMENDED, "load", "LD-1", "cycle time corrected")
    assert str(event).endswith(", cycle time corrected")


def test_rebuilding_from_storage_gives_the_same_chain() -> None:
    made = trail()
    again = rebuild(made.events)
    assert again.head == made.head
    assert again.intact()
