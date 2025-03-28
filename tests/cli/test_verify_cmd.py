from __future__ import annotations

from datetime import date

import pytest

from sterilot.store.store import Store
from tests.cli.conftest import add_washer, invoke


@pytest.fixture
def decon(db: str) -> str:
    add_washer(db)
    invoke(db, "wash", "seed-standard")
    return db


def test_a_soil_device_pass_is_recorded(decon: str) -> None:
    result = invoke(decon, "verify", "soil", "WD-2")
    assert result.exit_code == 0
    assert "soil device passed on WD-2" in result.output


def test_a_soil_device_failure_is_recorded(decon: str) -> None:
    result = invoke(decon, "verify", "soil", "WD-2", "--failed")
    assert result.exit_code == 0
    assert "failed" in result.output


def test_a_clean_residue_test_passes(decon: str) -> None:
    result = invoke(decon, "verify", "residue", "WD-2", "atp", "--value", "40")
    assert result.exit_code == 0
    assert "inside" in result.output


def test_a_dirty_residue_test_exits_with_the_policy_status(decon: str) -> None:
    result = invoke(
        decon, "verify", "residue", "WD-2", "protein", "--value", "9", "--subject", "SU-1234"
    )
    assert result.exit_code == 5
    assert "SU-1234" in result.output
    assert "over" in result.output


def test_an_unknown_test_is_a_validation_failure(decon: str) -> None:
    result = invoke(decon, "verify", "residue", "WD-2", "swab", "--value", "1")
    assert result.exit_code == 2


def test_the_day_lists_what_was_run(decon: str) -> None:
    invoke(decon, "verify", "soil", "WD-2")
    invoke(decon, "verify", "residue", "WD-2", "atp", "--value", "40")
    today = date.today().isoformat()
    result = invoke(decon, "verify", "day", "WD-2", "--on", today)
    assert "soil device" in result.output
    assert "atp" in result.output
    assert "no passing soil device test" not in result.output


def test_a_day_with_no_soil_test_says_so(decon: str) -> None:
    invoke(decon, "verify", "residue", "WD-2", "atp", "--value", "40")
    today = date.today().isoformat()
    result = invoke(decon, "verify", "day", "WD-2", "--on", today)
    assert "no passing soil device test that day" in result.output


def test_the_suspect_window_runs_back_to_the_last_pass(decon: str) -> None:
    invoke(decon, "verify", "soil", "WD-2")
    invoke(decon, "verify", "soil", "WD-2", "--failed")
    with Store.open(decon) as store:
        results = store.verifications.for_equipment("WD-2")
        failure = next(item for item in results if not item.passed)
    result = invoke(
        decon, "verify", "suspect", "WD-2", "--at", failure.at.strftime("%Y-%m-%d %H:%M:%S")
    )
    assert result.exit_code == 0
    assert "is suspect from" in result.output
    assert "no wash cycles recorded" in result.output


def test_a_moment_with_no_failure_is_refused(decon: str) -> None:
    invoke(decon, "verify", "soil", "WD-2")
    result = invoke(decon, "verify", "suspect", "WD-2", "--at", "2025-04-01 09:00")
    assert result.exit_code == 2


def test_the_log_reads_back_through_the_store(decon: str) -> None:
    invoke(decon, "verify", "soil", "WD-2")
    with Store.open(decon) as store:
        log = store.verifications.log()
        assert len(log.results) == 1
        assert store.verifications.verified_on("WD-2", date.today())
