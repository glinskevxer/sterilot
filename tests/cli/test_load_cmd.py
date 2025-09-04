from __future__ import annotations

from click.testing import Result

from tests.cli.conftest import add_sterilizer, assemble, invoke, record_cycle

LOT = "AC-1-20250114-01"


def build(db: str, *extra: str) -> Result:
    return invoke(db, "load", "build", "LD-1", "--lot", LOT, "--tray", "ORT-0114", *extra)


def release(db: str, *extra: str) -> Result:
    return invoke(
        db,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "ORT-0114",
        "--internal",
        "ORT-0114",
        *extra,
    )


def test_a_load_builds_against_a_recorded_cycle(ready: str) -> None:
    result = build(ready)
    assert result.exit_code == 0
    assert "built LD-1 (1 items) on AC-1-20250114-01" in result.output


def test_building_against_an_unknown_lot_exits_not_found(ready: str) -> None:
    result = invoke(
        ready, "load", "build", "LD-9", "--lot", "AC-1-20250114-09", "--tray", "ORT-0114"
    )
    assert result.exit_code == 3


def test_building_with_an_unknown_tray_exits_not_found(ready: str) -> None:
    result = invoke(ready, "load", "build", "LD-9", "--lot", LOT, "--tray", "XX-1")
    assert result.exit_code == 3


def test_a_clean_load_releases(ready: str) -> None:
    build(ready)
    result = release(ready)
    assert result.exit_code == 0
    assert "released routine" in result.output


def test_a_load_with_no_internal_indicator_is_rejected(ready: str) -> None:
    build(ready)
    result = invoke(
        ready,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "ORT-0114",
    )
    assert result.exit_code == 5
    assert "no internal indicator" in result.output


def test_a_failed_strip_is_named_against_its_tray(ready: str) -> None:
    build(ready)
    result = release(ready, "--internal", "ORT-0114=fail")
    assert result.exit_code == 5
    assert "the internal indicator failed" in result.output


def test_a_wet_load_is_rejected(ready: str) -> None:
    build(ready)
    result = release(ready, "--wet")
    assert result.exit_code == 5
    assert "came out wet" in result.output


def test_a_missing_air_removal_test_rejects_the_load(db: str) -> None:
    add_sterilizer(db)
    assemble(db, "ORT-0114")
    record_cycle(db, "2025-01-14 08:00")
    build(db)
    result = release(db)
    assert result.exit_code == 5
    assert "no passing air removal test" in result.output


def test_an_implant_load_is_held_until_the_biological_is_read(ready: str) -> None:
    invoke(
        ready, "load", "build", "LD-1", "--lot", LOT, "--tray", "IMP-0001", "--implant", "IMP-0001"
    )
    result = invoke(
        ready,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
    )
    assert result.exit_code == 5
    assert "carries an implant" in result.output


def test_an_implant_load_releases_once_the_biological_reads(ready: str) -> None:
    invoke(
        ready, "load", "build", "LD-1", "--lot", LOT, "--tray", "IMP-0001", "--implant", "IMP-0001"
    )
    result = invoke(
        ready,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
        "--biological",
        "pass",
    )
    assert result.exit_code == 0
    assert "released implant" in result.output


def test_a_failed_biological_rejects_the_load(ready: str) -> None:
    build(ready)
    result = release(ready, "--biological", "fail")
    assert result.exit_code == 5
    assert "the biological indicator grew" in result.output


def test_show_prints_the_load_and_its_reasons(ready: str) -> None:
    build(ready)
    release(ready, "--wet")
    result = invoke(ready, "load", "show", "LD-1")
    assert result.exit_code == 0
    assert "rejected" in result.output
    assert "came out wet" in result.output
    assert "ORT-0114" in result.output


def test_held_loads_are_listed(ready: str) -> None:
    invoke(
        ready, "load", "build", "LD-1", "--lot", LOT, "--tray", "IMP-0001", "--implant", "IMP-0001"
    )
    invoke(
        ready,
        "load",
        "release",
        "LD-1",
        "--ci-lot",
        "CI-25A01",
        "--ci-expires",
        "2026-01-31",
        "--external",
        "IMP-0001",
        "--internal",
        "IMP-0001",
    )
    result = invoke(ready, "load", "held")
    assert "LD-1" in result.output
    assert "implant" in result.output


def test_loads_of_a_tray_are_listed(ready: str) -> None:
    build(ready)
    result = invoke(ready, "load", "of-tray", "ort 0114")
    assert "LD-1" in result.output
    assert "pending" in result.output


def test_a_load_is_built_from_assembled_trays(db: str) -> None:
    add_sterilizer(db)
    invoke(db, "tray", "register", "ORT-0114", "ORT-MAJOR")
    record_cycle(db, "2025-01-14 08:00")
    result = build(db)
    assert result.exit_code != 0
    assert "is soiled, a load is built from assembled trays" in result.output


def test_building_a_load_puts_the_trays_in_the_chamber(ready: str) -> None:
    build(ready)
    shown = invoke(ready, "tray", "show", "ORT-0114", "--no-history")
    assert "sterilizing" in shown.output


def test_releasing_a_load_walks_its_trays_onto_the_shelf(ready: str) -> None:
    build(ready)
    release(ready)
    shown = invoke(ready, "tray", "show", "ORT-0114")
    assert "cooling" in shown.output
    assert "stage      sterile" in shown.output


def test_a_rejected_load_leaves_its_trays_in_the_chamber(ready: str) -> None:
    build(ready)
    release(ready, "--wet")
    shown = invoke(ready, "tray", "show", "ORT-0114", "--no-history")
    assert "sterilizing" in shown.output


def with_sheet(db: str, grams: int) -> None:
    invoke(
        db,
        "catalog",
        "add",
        "SU-1234",
        "kelly forceps",
        "--manufacturer",
        "V Mueller",
        "--complexity",
        "hinged",
        "--grams",
        str(grams),
    )
    invoke(
        db,
        "sheet",
        "define",
        "ORT-MAJOR",
        "orthopaedic major set",
        "--line",
        "SU-1234=4",
        "--from",
        "2025-01-01",
    )


def test_a_load_takes_its_weight_from_the_count_sheet(ready: str) -> None:
    with_sheet(ready, 3000)
    result = build(ready)
    assert result.exit_code == 0
    assert "over the set weight limit" in result.output


def test_a_set_inside_the_limit_says_nothing(ready: str) -> None:
    with_sheet(ready, 500)
    result = build(ready)
    assert result.exit_code == 0
    assert "weight" not in result.output


def test_a_sheet_with_a_missing_weight_is_not_guessed_at(ready: str) -> None:
    invoke(
        ready,
        "catalog",
        "add",
        "SU-1234",
        "kelly forceps",
        "--manufacturer",
        "V Mueller",
        "--complexity",
        "hinged",
        "--grams",
        "3000",
    )
    invoke(
        ready,
        "catalog",
        "add",
        "SU-1235",
        "kocher forceps",
        "--manufacturer",
        "V Mueller",
        "--complexity",
        "hinged",
    )
    invoke(
        ready,
        "sheet",
        "define",
        "ORT-MAJOR",
        "orthopaedic major set",
        "--line",
        "SU-1234=4",
        "--line",
        "SU-1235=1",
        "--from",
        "2025-01-01",
    )
    result = build(ready)
    assert result.exit_code == 0
    assert "over the set weight limit" not in result.output


def test_a_set_with_no_sheet_at_all_still_builds(ready: str) -> None:
    result = build(ready)
    assert result.exit_code == 0
    assert "built LD-1" in result.output
