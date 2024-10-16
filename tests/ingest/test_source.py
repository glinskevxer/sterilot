from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.ingest.source import (
    Row,
    RowProblem,
    normalise_column,
    read_delimited,
    sniff_delimiter,
)

CSV = "cycle,sterilizer,temp\n1,AC-1,133.0\n2,AC-1,132.4\n"


def test_a_row_reads_its_own_values() -> None:
    row = Row(2, {"cycle": "1", "note": "  "})
    assert row.get("cycle") == "1"
    assert row.get("missing", "x") == "x"
    assert row.has("cycle")
    assert not row.has("note")
    assert row.require("cycle") == "1"


def test_requiring_an_empty_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        Row(2, {"note": "   "}).require("note")


@pytest.mark.parametrize(
    ("name", "clean"),
    [
        ("Cycle Number", "cycle_number"),
        (" STERILIZER ", "sterilizer"),
        ("temp.max", "temp_max"),
        ("a/b", "a_b"),
        ("double  space", "double_space"),
        ("﻿cycle", "cycle"),
    ],
)
def test_column_names_are_normalised(name: str, clean: str) -> None:
    assert normalise_column(name) == clean


@pytest.mark.parametrize(
    ("text", "delimiter"),
    [
        ("a,b,c\n1,2,3\n", ","),
        ("a\tb\tc\n1\t2\t3\n", "\t"),
        ("a;b;c\n1;2;3\n", ";"),
        ("a|b|c\n1|2|3\n", "|"),
    ],
)
def test_the_delimiter_is_sniffed(text: str, delimiter: str) -> None:
    assert sniff_delimiter(text) == delimiter


def test_a_file_with_one_column_cannot_be_sniffed() -> None:
    with pytest.raises(ValidationError):
        sniff_delimiter("cycle\n1\n")


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(ValidationError):
        read_delimited("   ")
    with pytest.raises(ValidationError):
        sniff_delimiter("\n\n")


def test_a_clean_file_reads_every_row() -> None:
    result = read_delimited(CSV)
    assert result.clean
    assert len(result.rows) == 2
    assert result.columns == ("cycle", "sterilizer", "temp")
    assert result.rows[0].values["temp"] == "133.0"
    assert result.summary() == "2 rows read, 0 rejected"


def test_a_byte_order_mark_does_not_break_the_header() -> None:
    result = read_delimited("﻿" + CSV)
    assert result.columns[0] == "cycle"


def test_blank_lines_are_skipped() -> None:
    result = read_delimited("cycle,temp\n\n1,133\n\n2,132\n")
    assert len(result.rows) == 2


def test_fields_are_stripped() -> None:
    result = read_delimited("cycle , temp\n 1 , 133.0 \n")
    assert result.rows[0].values == {"cycle": "1", "temp": "133.0"}


def test_quoted_fields_survive_the_delimiter() -> None:
    result = read_delimited('cycle,note\n1,"held, then released"\n')
    assert result.rows[0].values["note"] == "held, then released"


def test_a_missing_required_column_stops_the_read() -> None:
    with pytest.raises(ValidationError) as caught:
        read_delimited(CSV, required=["cycle", "load"])
    assert caught.value.context["columns"] == ["load"]


def test_an_alias_maps_a_foreign_header() -> None:
    text = "Cycle No,Unit,Temp\n1,AC-1,133\n"
    result = read_delimited(
        text, required=["cycle"], aliases={"cycle_no": "cycle", "unit": "sterilizer"}
    )
    assert result.rows[0].values["cycle"] == "1"
    assert result.rows[0].values["sterilizer"] == "AC-1"


def test_a_short_row_is_rejected_and_the_rest_still_read() -> None:
    result = read_delimited("cycle,sterilizer,temp\n1,AC-1\n2,AC-1,132.4\n")
    assert len(result.rows) == 1
    assert not result.clean
    assert result.problems[0].describe() == "row 2 has the wrong number of fields: 2 not 3"


def test_a_row_missing_a_required_value_is_rejected() -> None:
    result = read_delimited("cycle,sterilizer\n1,\n2,AC-1\n", required=["sterilizer"])
    assert len(result.rows) == 1
    assert result.problems[0].describe() == "row 2 is missing values: sterilizer"


def test_a_problem_without_detail_reads_plainly() -> None:
    assert RowProblem(3, "is unreadable").describe() == "row 3 is unreadable"


def test_an_explicit_delimiter_overrides_the_sniff() -> None:
    result = read_delimited("a;b\n1;2\n", delimiter=";")
    assert result.columns == ("a", "b")
