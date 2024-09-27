from __future__ import annotations

from datetime import date, datetime

import pytest

from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.money import Money
from sterilot.repair.order import RepairBook, RepairOrder, Status
from sterilot.staff.tech import Role, Technician

RAISED = datetime(2024, 9, 2, 9, 0)
SENT = datetime(2024, 9, 3, 9, 0)


def order(**changes: object) -> RepairOrder:
    values: dict[str, object] = {
        "reference": "rp 2201",
        "asset": "inst 0912",
        "catalog": "su 2000",
        "tray_code_out_of": "ort major",
        "vendor": "Sharpline Repair",
        "fault": "blade will not close",
        "raised_at": RAISED,
        "raised_by": "t 4471",
    }
    values.update(changes)
    return RepairOrder(**values)  # type: ignore[arg-type]


def person(role: Role = Role.SUPERVISOR, badge: str = "T-9900") -> Technician:
    return Technician(badge, "M Iqbal", role)


def test_status_lookup_and_grouping() -> None:
    assert Status.named("scrapped") is Status.SCRAPPED
    assert Status.RETURNED.closed
    assert not Status.SENT.closed
    assert Status.QUOTED.away
    assert not Status.RAISED.away
    with pytest.raises(ValidationError):
        Status.named("lost in the post")


def test_identifiers_are_normalised_and_details_required() -> None:
    made = order()
    assert made.reference == "RP-2201"
    assert made.asset == "INST-0912"
    assert made.tray_code_out_of == "ORT-MAJOR"
    with pytest.raises(ValidationError):
        order(vendor=" ")
    with pytest.raises(ValidationError):
        order(fault="")


def test_an_approved_order_carries_a_quote() -> None:
    with pytest.raises(ValidationError):
        order(status=Status.APPROVED)


def test_a_closed_order_records_when() -> None:
    with pytest.raises(ValidationError):
        order(status=Status.RETURNED)


def test_the_state_machine_refuses_a_jump() -> None:
    with pytest.raises(ConflictError):
        order().moved_to(Status.RETURNED, SENT)


def test_a_repair_walks_sent_quoted_approved_returned() -> None:
    made = order().moved_to(Status.SENT, SENT)
    assert made.sent_at == SENT
    made = made.moved_to(Status.QUOTED, datetime(2024, 9, 6, 9, 0))
    made = made.approved(datetime(2024, 9, 7, 9, 0), person(Role.LEAD), Money.of_dollars(120))
    assert made.status is Status.APPROVED
    assert made.approved_by == "T-9900"
    made = made.moved_to(Status.RETURNED, datetime(2024, 9, 20, 9, 0))
    assert not made.open
    assert made.closed_at == datetime(2024, 9, 20, 9, 0)


def test_a_quote_over_the_threshold_needs_a_supervisor() -> None:
    quoted = order().moved_to(Status.SENT, SENT).moved_to(Status.QUOTED, SENT)
    with pytest.raises(ConflictError):
        quoted.approved(SENT, person(Role.LEAD), Money.of_dollars(900))
    approved = quoted.approved(SENT, person(Role.SUPERVISOR), Money.of_dollars(900))
    assert approved.needs_supervisor()


def test_a_small_quote_can_be_approved_by_a_lead() -> None:
    quoted = order().moved_to(Status.SENT, SENT).moved_to(Status.QUOTED, SENT)
    approved = quoted.approved(SENT, person(Role.LEAD), Money.of_dollars(120))
    assert not approved.needs_supervisor()


def test_days_out_counts_from_the_day_it_left() -> None:
    made = order().moved_to(Status.SENT, SENT)
    assert made.days_out(date(2024, 9, 13)) == 10
    assert order().days_out(date(2024, 9, 13)) is None


def test_days_out_stops_when_it_comes_back() -> None:
    made = (
        order().moved_to(Status.SENT, SENT).moved_to(Status.RETURNED, datetime(2024, 9, 10, 9, 0))
    )
    assert made.days_out(date(2024, 10, 1)) == 7


def test_overdue_only_applies_while_it_is_away() -> None:
    made = order().moved_to(Status.SENT, SENT)
    assert not made.overdue(date(2024, 9, 20))
    assert made.overdue(date(2024, 10, 20))
    back = made.moved_to(Status.RETURNED, datetime(2024, 10, 20, 9, 0))
    assert not back.overdue(date(2024, 11, 1))


def test_the_book_refuses_a_duplicate_reference() -> None:
    book = RepairBook.of([order()])
    with pytest.raises(ConflictError):
        book.with_order(order())


def test_the_book_finds_and_replaces() -> None:
    book = RepairBook.of([order(), order(reference="RP-2202", asset="INST-0913")])
    assert book.get("rp 2201").asset == "INST-0912"
    sent = book.get("RP-2201").moved_to(Status.SENT, SENT)
    book = book.replacing(sent)
    assert book.get("RP-2201").status is Status.SENT
    with pytest.raises(NotFoundError):
        book.get("RP-9999")
    with pytest.raises(NotFoundError):
        RepairBook().replacing(order())


def test_open_orders_and_what_is_shorting_a_set() -> None:
    away = order().moved_to(Status.SENT, SENT)
    other = order(reference="RP-2202", asset="INST-0913", tray_code_out_of="GEN-MINOR")
    book = RepairBook.of([away, other])
    assert len(book.open_orders()) == 2
    assert [item.reference for item in book.away_from("ort major")] == ["RP-2201"]
    assert book.away_from("GEN-MINOR") == ()


def test_the_book_lists_what_is_overdue() -> None:
    away = order().moved_to(Status.SENT, SENT)
    book = RepairBook.of([away])
    assert [item.reference for item in book.overdue(date(2024, 11, 1))] == ["RP-2201"]
    assert book.overdue(date(2024, 9, 5)) == ()


def test_spend_counts_approved_and_returned_only() -> None:
    approved = (
        order()
        .moved_to(Status.SENT, SENT)
        .moved_to(Status.QUOTED, SENT)
        .approved(SENT, person(), Money.of_dollars(120))
    )
    quoted = order(
        reference="RP-2202", asset="INST-0913", status=Status.QUOTED, quote=Money.of_dollars(90)
    )
    book = RepairBook.of([approved, quoted])
    assert book.spend() == Money.of_dollars(120)


def test_summary_reads_like_the_bench_list() -> None:
    assert order().summary() == "RP-2201 INST-0912 raised"
    quoted = order(status=Status.QUOTED, quote=Money.of_dollars(120))
    assert str(quoted) == "RP-2201 INST-0912 quoted $120.00"
