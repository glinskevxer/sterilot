from __future__ import annotations

from pathlib import Path

import pytest

from sterilot.errors import ConfigurationError, ValidationError
from sterilot.settings import Settings


def test_defaults_are_a_working_department() -> None:
    settings = Settings()
    assert settings.facility == "Central Service"
    assert settings.set_weight_limit_kg == pytest.approx(11.4)
    assert settings.implant_hold_required
    assert settings.event_related_sterility


def test_a_shelf_life_turns_off_event_related_sterility() -> None:
    assert not Settings(shelf_life_days=180).event_related_sterility


@pytest.mark.parametrize(
    "values",
    [
        {"facility": "  "},
        {"set_weight_limit_kg": 0.0},
        {"shelf_life_days": 0},
        {"bi_incubation_hours": 0.0},
        {"loaner_lead_hours": -1},
        {"max_daily_runs": 0},
        {"max_daily_runs": 100},
        {"cooling_minutes": -5},
    ],
)
def test_indefensible_values_are_refused(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)  # type: ignore[arg-type]


def test_from_mapping_accepts_a_partial_table() -> None:
    settings = Settings.from_mapping({"facility": "Ridgeway CS", "loaner_lead_hours": 24})
    assert settings.facility == "Ridgeway CS"
    assert settings.loaner_lead_hours == 24
    assert settings.bi_incubation_hours == pytest.approx(24.0)


def test_from_mapping_names_the_keys_it_does_not_know() -> None:
    with pytest.raises(ConfigurationError) as caught:
        Settings.from_mapping({"facilty": "typo", "colour": "blue"})
    assert caught.value.context["keys"] == ["colour", "facilty"]


def test_load_reads_a_sterilot_section(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.toml"
    path.write_text(
        "[sterilot]\nfacility = 'Ridgeway CS'\nshelf_life_days = 180\n",
        encoding="utf-8",
    )
    settings = Settings.load(path)
    assert settings.facility == "Ridgeway CS"
    assert settings.shelf_life_days == 180


def test_load_accepts_a_bare_table(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.toml"
    path.write_text("facility = 'Bare'\n", encoding="utf-8")
    assert Settings.load(path).facility == "Bare"


def test_load_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        Settings.load(tmp_path / "nothing.toml")


def test_load_refuses_a_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.toml"
    path.write_text("this is not = = toml\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        Settings.load(path)


def test_load_refuses_a_sterilot_key_that_is_not_a_table(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.toml"
    path.write_text("sterilot = 4\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        Settings.load(path)


def test_load_or_default(tmp_path: Path) -> None:
    assert Settings.load_or_default(None) == Settings()
    path = tmp_path / "sterilot.toml"
    path.write_text("[sterilot]\nfacility = 'Named'\n", encoding="utf-8")
    assert Settings.load_or_default(path).facility == "Named"


def test_with_values_returns_a_new_settings() -> None:
    settings = Settings()
    changed = settings.with_values(loaner_lead_hours=12)
    assert changed.loaner_lead_hours == 12
    assert settings.loaner_lead_hours == 48


def test_describe_covers_every_field() -> None:
    described = Settings().describe()
    assert described["facility"] == "Central Service"
    assert set(described) == set(Settings.__dataclass_fields__)


def test_the_settings_write_out_as_a_readable_file() -> None:
    text = Settings().to_toml()
    assert text.startswith("[sterilot]")
    assert "facility = 'Central Service'" in text
    assert "implant_hold_required = true" in text
    assert "# how long a load cools before anybody touches it" in text


def test_an_unset_shelf_life_is_written_out_commented() -> None:
    assert "# shelf_life_days is not set" in Settings().to_toml()
    assert "shelf_life_days = 180" in Settings(shelf_life_days=180).to_toml()


def test_the_default_settings_round_trip_through_a_file(tmp_path: Path) -> None:
    path = tmp_path / "sterilot.toml"
    path.write_text(Settings().to_toml(), encoding="utf-8")
    assert Settings.load(path) == Settings()


def test_the_written_file_reads_back(tmp_path: Path) -> None:
    settings = Settings(facility="Ridgeway CS", loaner_lead_hours=24, shelf_life_days=180)
    path = tmp_path / "sterilot.toml"
    path.write_text(settings.to_toml(), encoding="utf-8")
    assert Settings.load(path) == settings


def test_every_field_carries_a_note() -> None:
    from sterilot.settings import NOTES

    assert set(NOTES) == set(Settings.__dataclass_fields__)
