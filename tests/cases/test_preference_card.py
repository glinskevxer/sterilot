from __future__ import annotations

from datetime import date

import pytest

from sterilot.cases.preference_card import CardFile, CardLine, PreferenceCard
from sterilot.errors import NotFoundError, ValidationError
from sterilot.interval import DateRange

DAY = date(2024, 9, 1)


def card(**changes: object) -> PreferenceCard:
    values: dict[str, object] = {
        "reference": "pc 118",
        "surgeon": "Okonkwo",
        "procedure": "total knee revision",
        "lines": [
            CardLine("ort major", quantity=2),
            CardLine("GEN-MINOR", essential=False, note="if available"),
        ],
        "effective": DateRange.starting(date(2024, 1, 1)),
    }
    values.update(changes)
    return PreferenceCard.of(**values)  # type: ignore[arg-type]


def test_a_line_normalises_its_code_and_needs_a_quantity() -> None:
    line = CardLine("ort major")
    assert line.code == "ORT-MAJOR"
    with pytest.raises(ValidationError):
        CardLine("ORT-MAJOR", quantity=0)


def test_a_line_describes_itself() -> None:
    assert CardLine("ORT-MAJOR", 2).describe() == "2 x ORT-MAJOR (essential)"
    assert CardLine("GEN-MINOR", essential=False, note="if available").describe() == (
        "1 x GEN-MINOR (preferred), if available"
    )


def test_a_card_needs_a_surgeon_a_procedure_and_lines() -> None:
    with pytest.raises(ValidationError):
        card(surgeon=" ")
    with pytest.raises(ValidationError):
        card(procedure="")
    with pytest.raises(ValidationError):
        card(lines=[])


def test_a_set_cannot_be_on_two_lines() -> None:
    with pytest.raises(ValidationError):
        card(lines=[CardLine("ORT-MAJOR"), CardLine("ort major")])


def test_revisions_are_numbered_from_one() -> None:
    with pytest.raises(ValidationError):
        card(revision=0)


def test_the_card_answers_what_it_wants() -> None:
    made = card()
    assert made.reference == "PC-118"
    assert made.total_sets == 3
    assert made.wanted() == {"ORT-MAJOR": 2, "GEN-MINOR": 1}
    assert made.wanted(essential_only=True) == {"ORT-MAJOR": 2}


def test_line_lookup_normalises() -> None:
    assert card().line_for("ort major").quantity == 2
    assert card().calls_for("GEN-MINOR")
    assert not card().calls_for("CYS-1")
    with pytest.raises(NotFoundError):
        card().line_for("CYS-1")


def test_loaner_sets_are_flagged() -> None:
    assert not card().needs_loaner
    assert card(loaner_sets=("revision knee tray 2",)).needs_loaner


def test_a_card_is_in_force_over_its_window() -> None:
    made = card(effective=DateRange(date(2024, 1, 1), date(2024, 6, 1)))
    assert made.in_force_on(date(2024, 3, 1))
    assert not made.in_force_on(DAY)


def test_revising_opens_the_next_version() -> None:
    revised = card().revised([CardLine("ORT-MAJOR", 3)], date(2024, 7, 1))
    assert revised.revision == 2
    assert revised.wanted() == {"ORT-MAJOR": 3}
    assert revised.effective.start == date(2024, 7, 1)


def test_a_revision_cannot_start_before_the_card_it_replaces() -> None:
    with pytest.raises(ValidationError):
        card().revised([CardLine("ORT-MAJOR")], date(2023, 1, 1))


def test_the_card_file_finds_the_version_in_force() -> None:
    first = card(effective=DateRange(date(2024, 1, 1), date(2024, 7, 1)))
    second = first.revised([CardLine("ORT-MAJOR", 3)], date(2024, 7, 1))
    file = CardFile().with_card(first).with_card(second)
    assert file.for_reference("PC-118", date(2024, 3, 1)).revision == 1
    assert file.for_reference("pc 118", DAY).revision == 2


def test_a_reference_with_no_card_in_force_is_refused() -> None:
    file = CardFile().with_card(card(effective=DateRange(date(2024, 1, 1), date(2024, 2, 1))))
    with pytest.raises(NotFoundError):
        file.for_reference("PC-118", DAY)


def test_cards_can_be_found_by_surgeon() -> None:
    other = card(reference="PC-119", surgeon="Bell", lines=[CardLine("CYS-1")])
    file = CardFile().with_card(card()).with_card(other)
    assert [item.reference for item in file.for_surgeon("okonkwo", DAY)] == ["PC-118"]
    assert file.for_surgeon("nobody", DAY) == ()


def test_sets_used_by_finds_every_card_calling_for_a_set() -> None:
    other = card(reference="PC-119", surgeon="Bell", lines=[CardLine("ORT-MAJOR")])
    file = CardFile().with_card(card()).with_card(other)
    assert file.sets_used_by("ort major", DAY) == ("PC-118", "PC-119")
    assert file.sets_used_by("CYS-1", DAY) == ()


def test_label() -> None:
    assert str(card()) == "PC-118 Okonkwo total knee revision rev 1"
