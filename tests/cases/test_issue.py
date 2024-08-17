from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.cases.issue import Disposition, Issue, IssueLog
from sterilot.errors import ConflictError, NotFoundError, ValidationError
from sterilot.recall.notice import Whereabouts

OUT = datetime(2024, 9, 4, 7, 0)
BACK = datetime(2024, 9, 4, 12, 0)


def issue(asset: str = "ort 0114", case: str = "or3 20240904 01", **changes: object) -> Issue:
    values: dict[str, object] = {
        "asset": asset,
        "case": case,
        "issued_at": OUT,
        "issued_by": "t 4471",
    }
    values.update(changes)
    return Issue(**values)  # type: ignore[arg-type]


def test_disposition_lookup_and_whereabouts() -> None:
    assert Disposition.named("USED") is Disposition.USED
    assert Disposition.OPEN.whereabouts is Whereabouts.ISSUED
    assert Disposition.UNOPENED.whereabouts is Whereabouts.STORAGE
    assert Disposition.OPENED.whereabouts is Whereabouts.REPROCESSING
    assert Disposition.USED.whereabouts is Whereabouts.USED
    with pytest.raises(ValidationError):
        Disposition.named("lost")


def test_identifiers_are_normalised() -> None:
    made = issue()
    assert made.asset == "ORT-0114"
    assert made.case == "OR3-20240904-01"
    assert made.issued_by == "T-4471"


def test_an_open_issue_has_no_return() -> None:
    made = issue()
    assert made.open
    assert made.whereabouts is Whereabouts.ISSUED
    assert made.describe() == "ORT-0114 out to OR3-20240904-01 since 2024-09-04 07:00"


def test_a_closed_issue_needs_a_return_time() -> None:
    with pytest.raises(ValidationError):
        issue(disposition=Disposition.USED)


def test_a_return_time_needs_a_disposition() -> None:
    with pytest.raises(ValidationError):
        issue(returned_at=BACK)


def test_a_tray_cannot_come_back_before_it_went_out() -> None:
    with pytest.raises(ValidationError):
        issue(returned_at=datetime(2024, 9, 4, 6, 0), disposition=Disposition.UNOPENED)


def test_returning_closes_the_issue() -> None:
    back = issue().returned(BACK, Disposition.UNOPENED)
    assert not back.open
    assert back.whereabouts is Whereabouts.STORAGE
    assert back.describe() == "ORT-0114 back from OR3-20240904-01 unopened"


def test_a_tray_cannot_be_returned_twice() -> None:
    back = issue().returned(BACK, Disposition.USED)
    with pytest.raises(ConflictError):
        back.returned(BACK, Disposition.USED)


def test_a_return_needs_a_real_disposition() -> None:
    with pytest.raises(ValidationError):
        issue().returned(BACK, Disposition.OPEN)


def test_the_log_refuses_to_issue_a_tray_that_is_already_out() -> None:
    log = IssueLog().with_entry(issue())
    with pytest.raises(ConflictError):
        log.with_entry(issue(case="OR4-20240904-02"))


def test_a_returned_tray_can_go_out_again() -> None:
    log = IssueLog().with_entry(issue())
    log = log.replacing(log.entries[0].returned(BACK, Disposition.OPENED))
    log = log.with_entry(issue(issued_at=datetime(2024, 9, 5, 7, 0)))
    assert len(log.entries) == 2


def test_replacing_an_issue_that_is_not_there_is_refused() -> None:
    with pytest.raises(NotFoundError):
        IssueLog().replacing(issue())


def test_the_log_filters_by_tray_and_by_case() -> None:
    log = IssueLog.of([issue(), issue(asset="GEN-0207", case="OR4-20240904-02")])
    assert [item.asset for item in log.for_asset("ort 0114")] == ["ORT-0114"]
    assert [item.asset for item in log.for_case("OR4-20240904-02")] == ["GEN-0207"]


def test_open_issues_are_listed() -> None:
    log = IssueLog.of([issue(), issue(asset="GEN-0207")])
    log = log.replacing(log.for_asset("GEN-0207")[0].returned(BACK, Disposition.USED))
    assert [item.asset for item in log.open_issues()] == ["ORT-0114"]


def test_whereabouts_reads_the_latest_issue() -> None:
    log = IssueLog().with_entry(issue())
    assert log.whereabouts("ORT-0114") == (Whereabouts.ISSUED, "OR3-20240904-01")
    log = log.replacing(log.entries[0].returned(BACK, Disposition.USED))
    assert log.whereabouts("ORT-0114") == (Whereabouts.USED, "OR3-20240904-01")


def test_a_tray_the_log_has_never_seen_is_unknown() -> None:
    assert IssueLog().whereabouts("XX-1") == (Whereabouts.UNKNOWN, "")


def test_locations_answers_for_a_whole_recall() -> None:
    log = IssueLog().with_entry(issue())
    found = log.locations(["ort 0114", "GEN-0207"])
    assert found["ORT-0114"][0] is Whereabouts.ISSUED
    assert found["GEN-0207"][0] is Whereabouts.UNKNOWN


def test_used_in_case_lists_only_the_trays_that_were_used() -> None:
    log = IssueLog.of([issue(), issue(asset="GEN-0207")])
    log = log.replacing(log.for_asset("ORT-0114")[0].returned(BACK, Disposition.USED))
    log = log.replacing(log.for_asset("GEN-0207")[0].returned(BACK, Disposition.UNOPENED))
    assert log.used_in_case("OR3-20240904-01") == ("ORT-0114",)


def test_the_latest_issue_is_the_last_one_out() -> None:
    log = IssueLog().with_entry(issue())
    log = log.replacing(log.entries[0].returned(BACK, Disposition.OPENED))
    later = issue(issued_at=datetime(2024, 9, 6, 7, 0), case="OR5-20240906-01")
    log = log.with_entry(later)
    latest = log.latest_for("ORT-0114")
    assert latest is not None
    assert latest.case == "OR5-20240906-01"
