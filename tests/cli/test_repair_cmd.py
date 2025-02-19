from __future__ import annotations

import pytest

from tests.cli.conftest import invoke


@pytest.fixture
def bench(db: str) -> str:
    invoke(db, "staff", "add", "T-4471", "R Ferreira")
    invoke(db, "staff", "add", "T-9002", "M Iqbal", "--role", "supervisor")
    invoke(
        db,
        "repair",
        "raise",
        "RP-1",
        "INST-0912",
        "--catalog",
        "SU-2000",
        "--from-set",
        "ORT-MAJOR",
        "--vendor",
        "Sharpline",
        "--fault",
        "blade will not close",
    )
    return db


def test_raising_an_order_reports_it(bench: str) -> None:
    result = invoke(
        bench,
        "repair",
        "raise",
        "RP-2",
        "INST-0913",
        "--catalog",
        "SU-2001",
        "--from-set",
        "GEN-MINOR",
        "--vendor",
        "Sharpline",
        "--fault",
        "loose pin",
    )
    assert result.exit_code == 0
    assert "RP-2 INST-0913 raised" in result.output


def test_a_reference_cannot_be_used_twice(bench: str) -> None:
    result = invoke(
        bench,
        "repair",
        "raise",
        "RP-1",
        "INST-0912",
        "--catalog",
        "SU-2000",
        "--from-set",
        "ORT-MAJOR",
        "--vendor",
        "Sharpline",
        "--fault",
        "again",
    )
    assert result.exit_code == 4


def test_an_order_walks_to_returned(bench: str) -> None:
    assert invoke(bench, "repair", "send", "RP-1").exit_code == 0
    quoted = invoke(bench, "repair", "quote", "RP-1", "120.00")
    assert "lead approval" in quoted.output
    approved = invoke(bench, "repair", "approve", "RP-1", badge="T-9002")
    assert "approved" in approved.output
    closed = invoke(bench, "repair", "close", "RP-1")
    assert "returned" in closed.output


def test_a_big_quote_needs_a_supervisor(bench: str) -> None:
    invoke(bench, "repair", "send", "RP-1")
    quoted = invoke(bench, "repair", "quote", "RP-1", "900.00")
    assert "supervisor approval" in quoted.output
    refused = invoke(bench, "repair", "approve", "RP-1")
    assert refused.exit_code == 4
    allowed = invoke(bench, "repair", "approve", "RP-1", badge="T-9002")
    assert allowed.exit_code == 0


def test_an_order_cannot_skip_a_step(bench: str) -> None:
    result = invoke(bench, "repair", "close", "RP-1")
    assert result.exit_code == 4


def test_approving_without_a_quote_is_refused(bench: str) -> None:
    invoke(bench, "repair", "send", "RP-1")
    result = invoke(bench, "repair", "approve", "RP-1", badge="T-9002")
    assert result.exit_code != 0
    assert "no quote to approve" in result.output


def test_open_orders_are_listed(bench: str) -> None:
    invoke(bench, "repair", "send", "RP-1")
    result = invoke(bench, "repair", "open")
    assert "RP-1" in result.output
    assert "sent" in result.output
    assert "days out" in result.output


def test_a_closed_order_leaves_the_open_list(bench: str) -> None:
    invoke(bench, "repair", "send", "RP-1")
    invoke(bench, "repair", "close", "RP-1")
    result = invoke(bench, "repair", "open")
    assert "RP-1" not in result.output


def test_what_is_shorting_a_set(bench: str) -> None:
    empty = invoke(bench, "repair", "shorting", "ort major")
    assert "nothing is out of ORT MAJOR" in empty.output
    invoke(bench, "repair", "send", "RP-1")
    result = invoke(bench, "repair", "shorting", "ORT-MAJOR")
    assert "INST-0912" in result.output
    assert "blade will not close" in result.output


def test_spend_counts_only_what_was_approved(bench: str) -> None:
    invoke(bench, "repair", "send", "RP-1")
    invoke(bench, "repair", "quote", "RP-1", "120.00")
    before = invoke(bench, "repair", "spend")
    assert "$0.00" in before.output
    invoke(bench, "repair", "approve", "RP-1", badge="T-9002")
    after = invoke(bench, "repair", "spend")
    assert "$120.00" in after.output


def test_an_unknown_reference_exits_not_found(bench: str) -> None:
    assert invoke(bench, "repair", "send", "RP-9").exit_code == 3
