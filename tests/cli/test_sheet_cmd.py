from __future__ import annotations

import pytest
from click.testing import Result

from tests.cli.conftest import invoke


@pytest.fixture
def catalog(db: str) -> str:
    for number, description in (("SU-1234", "kelly forceps"), ("SU-1235", "kocher forceps")):
        invoke(
            db,
            "catalog",
            "add",
            number,
            description,
            "--manufacturer",
            "V Mueller",
            "--complexity",
            "hinged",
            "--grams",
            "60",
        )
    return db


def define(db: str, *extra: str) -> Result:
    return invoke(
        db,
        "sheet",
        "define",
        "ORT-MAJOR",
        "orthopaedic major set",
        "--line",
        "SU-1234=6:stringer 1",
        "--from",
        "2025-01-01",
        *extra,
    )


def test_a_set_is_defined(catalog: str) -> None:
    result = define(catalog)
    assert result.exit_code == 0
    assert "ORT-MAJOR orthopaedic major set defined with 6 pieces" in result.output


def test_defining_the_same_set_twice_is_refused(catalog: str) -> None:
    define(catalog)
    result = define(catalog)
    assert result.exit_code != 0
    assert "already defined" in result.output


def test_a_line_naming_an_unstocked_item_exits_not_found(catalog: str) -> None:
    result = invoke(
        catalog,
        "sheet",
        "define",
        "GEN-MINOR",
        "general minor",
        "--line",
        "SU-9999=2",
        "--from",
        "2025-01-01",
    )
    assert result.exit_code == 3


def test_revising_opens_the_next_revision(catalog: str) -> None:
    define(catalog)
    result = invoke(
        catalog,
        "sheet",
        "revise",
        "ORT-MAJOR",
        "--line",
        "SU-1234=8",
        "--line",
        "SU-1235=2",
        "--from",
        "2025-06-01",
        "--note",
        "surgeon request",
    )
    assert result.exit_code == 0
    assert "ORT-MAJOR rev 2 in force from 2025-06-01" in result.output


def test_the_history_lists_every_revision(catalog: str) -> None:
    define(catalog)
    invoke(catalog, "sheet", "revise", "ORT-MAJOR", "--line", "SU-1234=8", "--from", "2025-06-01")
    result = invoke(catalog, "sheet", "history", "ORT-MAJOR")
    assert "2025-01-01 to 2025-05-31" in result.output
    assert "2025-06-01 onward" in result.output


def test_the_diff_says_what_moved(catalog: str) -> None:
    define(catalog)
    invoke(
        catalog,
        "sheet",
        "revise",
        "ORT-MAJOR",
        "--line",
        "SU-1234=8",
        "--line",
        "SU-1235=2",
        "--from",
        "2025-06-01",
    )
    result = invoke(catalog, "sheet", "diff", "ORT-MAJOR", "--from", "1", "--to", "2")
    assert "SU-1234 changed from 6 to 8" in result.output
    assert "SU-1235 added, 2" in result.output


def test_an_unchanged_diff_says_so(catalog: str) -> None:
    define(catalog)
    invoke(catalog, "sheet", "revise", "ORT-MAJOR", "--line", "SU-1234=6", "--from", "2025-06-01")
    result = invoke(catalog, "sheet", "diff", "ORT-MAJOR", "--from", "1", "--to", "2")
    assert "nothing changed" in result.output


def test_a_substitution_is_approved_and_listed(catalog: str) -> None:
    approved = invoke(
        catalog,
        "sheet",
        "substitute",
        "SU-1234",
        "SU-1235",
        "--from",
        "2025-01-01",
        "--reason",
        "original at repair",
    )
    assert approved.exit_code == 0
    assert "SU-1235 for SU-1234, original at repair" in approved.output
    listed = invoke(catalog, "sheet", "substitutions", "--on", "2025-05-01")
    assert "SU-1234" in listed.output


def test_a_substitution_naming_an_unstocked_item_exits_not_found(catalog: str) -> None:
    result = invoke(catalog, "sheet", "substitute", "SU-1234", "SU-9999", "--from", "2025-01-01")
    assert result.exit_code == 3


def test_an_expired_substitution_is_not_listed(catalog: str) -> None:
    invoke(
        catalog,
        "sheet",
        "substitute",
        "SU-1234",
        "SU-1235",
        "--from",
        "2025-01-01",
        "--to",
        "2025-03-01",
    )
    result = invoke(catalog, "sheet", "substitutions", "--on", "2025-05-01")
    assert "SU-1234" not in result.output


def test_the_check_passes_on_a_clean_catalog(catalog: str) -> None:
    define(catalog)
    result = invoke(catalog, "sheet", "check", "--on", "2025-05-01")
    assert "no problems found" in result.output


def test_the_check_names_a_missing_weight(catalog: str) -> None:
    invoke(catalog, "catalog", "add", "SU-2000", "scissors", "--manufacturer", "Aesculap")
    invoke(
        catalog,
        "sheet",
        "define",
        "GEN-MINOR",
        "general minor",
        "--line",
        "SU-2000=2",
        "--from",
        "2025-01-01",
    )
    result = invoke(catalog, "sheet", "check", "--on", "2025-05-01")
    assert "GEN-MINOR is missing a weight for SU-2000" in result.output
