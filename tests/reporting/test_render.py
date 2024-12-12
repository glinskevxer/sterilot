from __future__ import annotations

import pytest

from sterilot.errors import ValidationError
from sterilot.reporting.render import (
    Column,
    bullets,
    clip,
    heading,
    join,
    pairs,
    section,
    table,
)


def test_a_column_is_left_or_right() -> None:
    assert Column("name").align == "left"
    with pytest.raises(ValidationError):
        Column("name", align="centre")
    with pytest.raises(ValidationError):
        Column("name", width=0)


def test_clip_leaves_short_text_alone() -> None:
    assert clip("ORT-0114", 10) == "ORT-0114"


def test_clip_marks_what_it_cut() -> None:
    assert clip("orthopaedic major set", 12) == "orthopaed..."
    assert len(clip("orthopaedic major set", 12)) == 12


def test_clip_of_a_very_narrow_column_just_cuts() -> None:
    assert clip("orthopaedic", 2) == "or"
    with pytest.raises(ValidationError):
        clip("x", 0)


def test_a_table_sizes_itself_to_its_contents() -> None:
    rendered = table(
        [Column("asset"), Column("set")],
        [["ORT-0114", "ORT-MAJOR"], ["GEN-7", "GEN-MINOR"]],
    )
    lines = rendered.splitlines()
    assert lines[0] == "asset     set"
    assert lines[1] == "--------  ---------"
    assert lines[2] == "ORT-0114  ORT-MAJOR"


def test_numbers_can_be_right_aligned() -> None:
    rendered = table([Column("units", align="right")], [[4], [12]])
    lines = rendered.splitlines()
    assert lines[2] == "    4"
    assert lines[3] == "   12"


def test_booleans_and_nothing_render_readably() -> None:
    rendered = table([Column("implant"), Column("note")], [[True, None], [False, "x"]])
    lines = rendered.splitlines()
    assert lines[2].startswith("yes")
    assert lines[3].startswith("no")


def test_a_fixed_width_column_clips() -> None:
    rendered = table([Column("set", width=6)], [["orthopaedic major"]])
    assert rendered.splitlines()[2] == "ort..."


def test_a_table_with_no_rows_still_prints_its_header() -> None:
    rendered = table([Column("asset")], [])
    assert rendered.splitlines() == ["asset", "-----"]


def test_a_row_that_does_not_match_the_columns_is_refused() -> None:
    with pytest.raises(ValidationError):
        table([Column("a"), Column("b")], [["only one"]])


def test_a_table_needs_columns_and_a_gap() -> None:
    with pytest.raises(ValidationError):
        table([], [])
    with pytest.raises(ValidationError):
        table([Column("a")], [], gap=0)


def test_trailing_space_is_trimmed() -> None:
    rendered = table([Column("a"), Column("b")], [["x", ""]])
    assert rendered.splitlines()[2] == "x"


def test_pairs_line_up_their_labels() -> None:
    rendered = pairs([("facility", "Ridgeway"), ("loads", 4)])
    assert rendered.splitlines() == ["facility  Ridgeway", "loads     4"]
    assert pairs([]) == ""


def test_headings_underline_to_the_right_width() -> None:
    assert heading("Daily test log") == "Daily test log\n=============="
    assert heading("Loads", "-") == "Loads\n-----"


def test_a_heading_needs_words_and_one_underline_character() -> None:
    with pytest.raises(ValidationError):
        heading("  ")
    with pytest.raises(ValidationError):
        heading("Loads", "--")


def test_bullets() -> None:
    assert bullets(["first", "second"]) == "- first\n- second"
    assert bullets(["only"], marker="*") == "* only"
    assert bullets([]) == ""


def test_a_section_says_when_there_is_nothing() -> None:
    assert section("Holds", "") == "Holds\n-----\nnothing to report"
    assert section("Holds", "LD-1") == "Holds\n-----\nLD-1"


def test_blocks_are_stacked_with_one_blank_line() -> None:
    assert join(["first", "", "second\n"]) == "first\n\nsecond"
    assert join([]) == ""
