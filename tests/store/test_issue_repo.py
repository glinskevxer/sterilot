from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.cases.issue import Disposition, Issue
from sterilot.errors import ConflictError, NotFoundError
from sterilot.recall.notice import Whereabouts
from sterilot.store.db import Database
from sterilot.store.issue_repo import IssueStore
from sterilot.store.migrations import migrate

OUT = datetime(2024, 12, 9, 7, 0)
BACK = datetime(2024, 12, 9, 13, 0)


def store() -> IssueStore:
    db = Database.in_memory()
    migrate(db)
    return IssueStore(db)


def issue(asset: str = "ORT-0114", case: str = "OR3-20241209-01", at: datetime = OUT) -> Issue:
    return Issue(asset, case, at, "T-4471")


def test_an_issue_round_trips() -> None:
    issues = store()
    issues.save(issue())
    found = issues.get("ort 0114", OUT)
    assert found.case == "OR3-20241209-01"
    assert found.open
    issues.db.close()


def test_a_return_round_trips_with_its_disposition() -> None:
    issues = store()
    issues.save(issue().returned(BACK, Disposition.USED))
    found = issues.get("ORT-0114", OUT)
    assert not found.open
    assert found.disposition is Disposition.USED
    assert found.returned_at == BACK
    issues.db.close()


def test_an_unknown_issue_is_refused() -> None:
    issues = store()
    with pytest.raises(NotFoundError):
        issues.get("ORT-0114", OUT)
    issues.db.close()


def test_a_tray_cannot_be_issued_while_it_is_out() -> None:
    issues = store()
    issues.issue_out(issue())
    with pytest.raises(ConflictError):
        issues.issue_out(issue(at=datetime(2024, 12, 9, 9, 0)))
    issues.db.close()


def test_a_returned_tray_can_go_out_again() -> None:
    issues = store()
    issues.issue_out(issue())
    issues.save(issue().returned(BACK, Disposition.OPENED))
    issues.issue_out(issue(at=datetime(2024, 12, 10, 7, 0)))
    assert len(issues.for_asset("ORT-0114")) == 2
    issues.db.close()


def test_issues_are_filtered_by_case() -> None:
    issues = store()
    issues.save_all([issue(), issue("GEN-0207", "OR4-20241209-02")])
    assert [item.asset for item in issues.for_case("OR3-20241209-01")] == ["ORT-0114"]
    issues.db.close()


def test_open_issues_are_listed() -> None:
    issues = store()
    issues.save_all([issue(), issue("GEN-0207").returned(BACK, Disposition.UNOPENED)])
    assert [item.asset for item in issues.open_issues()] == ["ORT-0114"]
    assert issues.open_for("GEN-0207") is None
    issues.db.close()


def test_the_latest_issue_is_the_last_one_out() -> None:
    issues = store()
    issues.save(issue().returned(BACK, Disposition.OPENED))
    issues.save(issue(at=datetime(2024, 12, 11, 7, 0), case="OR5-20241211-01"))
    latest = issues.latest_for("ORT-0114")
    assert latest is not None
    assert latest.case == "OR5-20241211-01"
    issues.db.close()


def test_whereabouts_answers_from_the_latest_issue() -> None:
    issues = store()
    issues.save(issue())
    assert issues.whereabouts("ORT-0114") == (Whereabouts.ISSUED, "OR3-20241209-01")
    issues.save(issue().returned(BACK, Disposition.USED))
    assert issues.whereabouts("ORT-0114") == (Whereabouts.USED, "OR3-20241209-01")
    assert issues.whereabouts("XX-1") == (Whereabouts.UNKNOWN, "")
    issues.db.close()


def test_locations_answers_a_whole_recall() -> None:
    issues = store()
    issues.save(issue())
    found = issues.locations(["ort 0114", "GEN-0207"])
    assert found["ORT-0114"][0] is Whereabouts.ISSUED
    assert found["GEN-0207"][0] is Whereabouts.UNKNOWN
    issues.db.close()


def test_the_whole_log_can_be_read_back() -> None:
    issues = store()
    issues.save_all([issue(), issue("GEN-0207")])
    log = issues.log()
    assert len(log.entries) == 2
    assert log.open_issues()[0].asset == "ORT-0114"
    issues.db.close()
