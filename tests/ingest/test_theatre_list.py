from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ingest.theatre_list import load_theatre_list

LIST = """case,room,surgeon,procedure,start,minutes,card
OR3-01,OR3,Okonkwo,total knee revision,2025-04-22 08:00,120,PC-118
OR3-02,OR3,Okonkwo,total hip,2025-04-22 11:00,150,PC-119
OR4-01,OR4,Bell,cystoscopy,2025-04-22 08:30,45,
"""


def test_a_clean_list_reads_every_case() -> None:
    result = load_theatre_list(LIST)
    assert result.clean
    assert len(result.cases) == 3
    assert result.rooms() == ("OR3", "OR4")
    assert result.summary() == "3 cases read, 0 rows rejected"


def test_the_cases_carry_their_details() -> None:
    first = load_theatre_list(LIST).cases[0]
    assert first.case == "OR3-01"
    assert first.room == "OR3"
    assert first.starts_at == datetime(2025, 4, 22, 8, 0)
    assert first.minutes == 120
    assert first.card_reference == "PC-118"


def test_a_case_with_no_card_is_still_read() -> None:
    last = load_theatre_list(LIST).cases[2]
    assert last.card_reference == ""


def test_a_missing_duration_falls_back_to_the_default() -> None:
    text = LIST.replace(",120,PC-118", ",,PC-118")
    assert load_theatre_list(text).cases[0].minutes == 60


def test_a_duration_that_is_not_a_number_falls_back_too() -> None:
    text = LIST.replace(",120,PC-118", ",two hours,PC-118")
    assert load_theatre_list(text).cases[0].minutes == 60


def test_foreign_headers_are_aliased() -> None:
    text = LIST.replace(
        "case,room,surgeon,procedure,start,minutes,card",
        "Case No,Theatre,Consultant,Operation,Start Time,Duration,Preference Card",
    )
    result = load_theatre_list(text)
    assert len(result.cases) == 3
    assert result.cases[0].card_reference == "PC-118"


def test_a_row_that_will_not_build_is_reported() -> None:
    text = LIST.replace("2025-04-22 08:00", "sometime tuesday")
    result = load_theatre_list(text)
    assert len(result.cases) == 2
    assert "will not build a case" in result.problems[0].describe()


def test_a_repeated_case_number_is_reported_once() -> None:
    text = LIST + "OR3-01,OR3,Okonkwo,total knee revision,2025-04-22 14:00,120,PC-118\n"
    result = load_theatre_list(text)
    assert len(result.cases) == 3
    assert "repeat of a case" in result.problems[0].describe()


def test_a_short_row_is_rejected_and_the_rest_survive() -> None:
    text = LIST + "OR5-01,OR5\n"
    result = load_theatre_list(text)
    assert len(result.cases) == 3
    assert not result.clean


def test_a_file_missing_a_required_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        load_theatre_list("case,room\nOR3-01,OR3\n")


def test_a_row_missing_a_surgeon_is_rejected() -> None:
    text = LIST.replace("OR4-01,OR4,Bell", "OR4-01,OR4,")
    result = load_theatre_list(text)
    assert len(result.cases) == 2
    assert not result.clean
