from __future__ import annotations

from datetime import date

import pytest

from sterilot.catalog.substitution import Substitution, SubstitutionTable
from sterilot.errors import ConflictError, ValidationError
from sterilot.interval import DateRange

DAY = date(2024, 5, 1)


def approval(
    original: str = "SU-1234",
    replacement: str = "SU-1299",
    start: date = date(2024, 1, 1),
    end: date | None = None,
    ratio: int = 1,
    reason: str = "",
) -> Substitution:
    return Substitution(original, replacement, "T-4471", DateRange(start, end), ratio, reason)


def test_catalog_numbers_and_badge_are_normalised() -> None:
    entry = Substitution("su 1234", "su 1299", "t 4471", DateRange.starting(DAY))
    assert entry.original == "SU-1234"
    assert entry.replacement == "SU-1299"
    assert entry.approved_by == "T-4471"


def test_an_item_cannot_substitute_for_itself() -> None:
    with pytest.raises(ValidationError):
        approval("SU-1234", "su 1234")


def test_a_ratio_is_at_least_one() -> None:
    with pytest.raises(ValidationError):
        approval(ratio=0)


def test_quantity_scales_by_the_ratio() -> None:
    assert approval(ratio=2).quantity_for(3) == 6
    assert approval().quantity_for(3) == 3


def test_a_negative_quantity_is_refused() -> None:
    with pytest.raises(ValidationError):
        approval().quantity_for(-1)


def test_describe_reads_like_the_approval_form() -> None:
    assert approval().describe() == "SU-1299 for SU-1234"
    assert str(approval(ratio=2, reason="original at repair")) == (
        "SU-1299 for SU-1234 at 2 for 1, original at repair"
    )


def test_a_table_refuses_the_same_approval_twice() -> None:
    with pytest.raises(ConflictError):
        SubstitutionTable.of([approval(), approval()])


def test_the_same_pair_may_be_approved_again_from_a_later_day() -> None:
    table = SubstitutionTable.of(
        [
            approval(start=date(2024, 1, 1), end=date(2024, 3, 1)),
            approval(start=date(2024, 6, 1)),
        ]
    )
    assert len(table.entries) == 2


def test_an_expired_approval_is_not_active() -> None:
    table = SubstitutionTable.of([approval(start=date(2024, 1, 1), end=date(2024, 3, 1))])
    assert table.active(date(2024, 2, 1))
    assert not table.active(DAY)
    assert not table.accepts("SU-1234", "SU-1299", DAY)


def test_substitutions_are_directional() -> None:
    table = SubstitutionTable.of([approval()])
    assert table.accepts("SU-1234", "SU-1299", DAY)
    assert not table.accepts("SU-1299", "SU-1234", DAY)


def test_substitutions_do_not_chain() -> None:
    table = SubstitutionTable.of([approval("SU-A", "SU-B"), approval("SU-B", "SU-C")])
    assert table.accepts("SU-A", "SU-B", DAY)
    assert table.accepts("SU-B", "SU-C", DAY)
    assert not table.accepts("SU-A", "SU-C", DAY)


def test_replacements_for_lists_what_may_go_in() -> None:
    table = SubstitutionTable.of(
        [approval("SU-A", "SU-B"), approval("SU-A", "SU-C"), approval("SU-D", "SU-E")]
    )
    assert table.replacements_for("su a", DAY) == ("SU-B", "SU-C")


def test_find_returns_the_approval_itself() -> None:
    table = SubstitutionTable.of([approval(ratio=2)])
    found = table.find("SU-1234", "SU-1299", DAY)
    assert found is not None
    assert found.ratio == 2
    assert table.find("SU-1234", "SU-9999", DAY) is None


def test_with_entry_adds_without_touching_the_original() -> None:
    table = SubstitutionTable()
    grown = table.with_entry(approval())
    assert len(table.entries) == 0
    assert len(grown.entries) == 1


def test_retiring_closes_the_open_approval() -> None:
    table = SubstitutionTable.of([approval()])
    retired = table.retire("SU-1234", "SU-1299", date(2024, 7, 1))
    assert retired.entries[0].effective.end == date(2024, 7, 1)
    assert retired.accepts("SU-1234", "SU-1299", date(2024, 6, 30))
    assert not retired.accepts("SU-1234", "SU-1299", date(2024, 7, 1))


def test_retiring_a_pair_with_no_open_approval_is_refused() -> None:
    table = SubstitutionTable.of([approval(end=date(2024, 3, 1))])
    with pytest.raises(ValidationError):
        table.retire("SU-1234", "SU-1299", date(2024, 7, 1))


def test_retiring_leaves_other_pairs_alone() -> None:
    table = SubstitutionTable.of([approval("SU-A", "SU-B"), approval("SU-C", "SU-D")])
    retired = table.retire("SU-A", "SU-B", date(2024, 7, 1))
    assert retired.accepts("SU-C", "SU-D", date(2024, 8, 1))
