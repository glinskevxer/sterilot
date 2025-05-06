"""A whole day through the command line.

The unit tests hold one rule still. The store tests hold one table still. This
one runs the day the department actually has: the list arrives, the machines
are tested, trays go round, a load is released, a cart goes to a room, and then
a biological comes back positive and everything has to be found again.

It is slow and it is worth it, because every defect this suite has caught since
the store went in has been at a handover between two of these steps.
"""

from __future__ import annotations

import pytest

from tests.cli.conftest import add_sterilizer, add_washer, assemble, invoke, record_cycle

DAY = "2025-05-06"
LOT = "AC-1-20250506-01"
SECOND_LOT = "AC-1-20250506-02"


@pytest.fixture
def department(db: str) -> str:
    add_sterilizer(db)
    add_washer(db)
    invoke(db, "staff", "add", "T-4471", "R Ferreira")
    invoke(db, "staff", "add", "T-9002", "M Iqbal", "--role", "supervisor")
    invoke(
        db,
        "shelf",
        "add-location",
        "ST-A1",
        "rack A1",
        "--units",
        "24",
        "--floor-cm",
        "30",
        "--sprinkler-cm",
        "60",
    )
    invoke(db, "shelf", "par", "ORT-MAJOR", "--minimum", "1", "--target", "2")
    for number in ("SU-1234", "SU-1235"):
        invoke(
            db,
            "catalog",
            "add",
            number,
            "kelly forceps",
            "--manufacturer",
            "V Mueller",
            "--complexity",
            "hinged",
            "--grams",
            "60",
        )
    invoke(
        db,
        "sheet",
        "define",
        "ORT-MAJOR",
        "orthopaedic major set",
        "--line",
        "SU-1234=4",
        "--line",
        "SU-1235=2",
        "--from",
        "2025-01-01",
    )
    for asset in ("ORT-0114", "ORT-0115"):
        assemble(db, asset)
    return db


def build_and_release(db: str, reference: str, lot: str, asset: str) -> None:
    invoke(db, "load", "build", reference, "--lot", lot, "--tray", asset)
    invoke(
        db,
        "load",
        "release",
        reference,
        "--ci-lot",
        "CI-25E01",
        "--ci-expires",
        "2026-12-31",
        "--external",
        asset,
        "--internal",
        asset,
    )


def test_the_department_runs_a_day_and_then_recalls_it(department: str) -> None:
    db = department

    morning = invoke(db, "duty", "log", "AC-1", "air removal", "--on", DAY)
    assert morning.exit_code == 0
    assert invoke(db, "duty", "log", "AC-1", "biological", "--on", DAY).exit_code == 0
    assert invoke(db, "verify", "soil", "WD-2").exit_code == 0

    counted = invoke(
        db,
        "count",
        "tray",
        "ORT-MAJOR",
        "--item",
        "SU-1234=4",
        "--item",
        "SU-1235=2",
        "--on",
        DAY,
    )
    assert counted.exit_code == 0

    record_cycle(db, "2025-05-06 07:00", run=1)
    record_cycle(db, "2025-05-06 09:00", run=2)
    build_and_release(db, "LD-1", LOT, "ORT-0114")
    build_and_release(db, "LD-2", SECOND_LOT, "ORT-0115")
    assert "released" in invoke(db, "load", "show", "LD-1").output

    for asset, lot in (("ORT-0114", LOT), ("ORT-0115", SECOND_LOT)):
        assert (
            invoke(
                db, "shelf", "put", asset, lot, "--location", "ST-A1", "--set", "ORT-MAJOR"
            ).exit_code
            == 0
        )
    stock = invoke(db, "shelf", "stock")
    assert "ORT-MAJOR" in stock.output

    invoke(
        db,
        "schedule",
        "add-card",
        "PC-118",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--line",
        "ORT-MAJOR=2",
        "--from",
        "2025-01-01",
    )
    invoke(
        db,
        "schedule",
        "add-case",
        "OR3-01",
        "--room",
        "OR3",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--start",
        "2025-05-06 13:00",
        "--minutes",
        "120",
        "--card",
        "PC-118",
    )
    cart = invoke(db, "cart", "build", "CC-991", "OR3-01")
    assert cart.exit_code == 0
    assert "matches PC-118" in cart.output
    assert invoke(db, "cart", "deliver", "CC-991").exit_code == 0

    issued = invoke(db, "case", "issue", "OR3-01", "--tray", "ORT-0114")
    assert issued.exit_code == 0
    returned = invoke(db, "case", "return", "ORT-0114", "--as", "used")
    assert returned.exit_code == 0

    daily = invoke(db, "report", "daily", "--on", DAY)
    assert "2 loads" not in daily.output
    assert "LD-1" in daily.output
    assert "clean" in daily.output

    scope = invoke(db, "recall", "scope", "--equipment", "AC-1", "--at", "2025-05-06 18:00")
    assert "2 loads" in scope.output
    raised = invoke(
        db, "recall", "raise", "RC-2025-05", "--equipment", "AC-1", "--at", "2025-05-06 18:00"
    )
    assert raised.exit_code == 0
    assert "PATIENT EXPOSURE" in raised.output
    assert "marked 2 loads recalled" in raised.output

    assert "recalled" in invoke(db, "load", "show", "LD-1").output
    assert invoke(db, "quality", "audit").output.count("recalled") >= 1
    assert "chain intact" in invoke(db, "quality", "audit").output
    assert invoke(db, "health").exit_code == 0


def test_a_missing_daily_test_stops_the_release_and_shows_up_in_the_report(
    department: str,
) -> None:
    db = department
    record_cycle(db, "2025-05-06 07:00", run=1)
    invoke(db, "load", "build", "LD-1", "--lot", LOT, "--tray", "ORT-0114")
    result = invoke(
        db,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25E01",
        "--ci-expires",
        "2026-12-31",
        "--external",
        "ORT-0114",
        "--internal",
        "ORT-0114",
    )
    assert result.exit_code == 5
    assert "no passing air removal test" in result.output

    daily = invoke(db, "report", "daily", "--on", DAY)
    assert "AC-1 has no air removal test" in daily.output
    assert "see below" in daily.output

    compliance = invoke(db, "admin", "compliance", "--from", "2025-05-01", "--to", "2025-05-08")
    assert compliance.exit_code == 5
    assert "AC-1" in compliance.output


def test_the_shelf_and_the_list_disagree_when_stock_is_short(department: str) -> None:
    db = department
    invoke(db, "duty", "log", "AC-1", "air removal", "--on", DAY)
    invoke(db, "duty", "log", "AC-1", "biological", "--on", DAY)
    record_cycle(db, "2025-05-06 07:00", run=1)
    build_and_release(db, "LD-1", LOT, "ORT-0114")
    invoke(db, "shelf", "put", "ORT-0114", LOT, "--location", "ST-A1", "--set", "ORT-MAJOR")

    invoke(
        db,
        "schedule",
        "add-card",
        "PC-118",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--line",
        "ORT-MAJOR=2",
        "--from",
        "2025-01-01",
    )
    invoke(
        db,
        "schedule",
        "add-case",
        "OR3-01",
        "--room",
        "OR3",
        "--surgeon",
        "Okonkwo",
        "--procedure",
        "knee",
        "--start",
        "2025-05-06 13:00",
        "--minutes",
        "120",
        "--card",
        "PC-118",
    )
    demand = invoke(db, "schedule", "demand", "--on", DAY)
    lines = [line for line in demand.output.splitlines() if line.startswith("ORT-MAJOR")]
    assert lines[0].split()[-1] == "1"

    cart = invoke(db, "cart", "build", "CC-991", "OR3-01")
    assert cart.exit_code == 5
    assert "came up 1 short" in cart.output
