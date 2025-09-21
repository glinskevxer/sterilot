"""The names the package exports, held still.

An embedding application imports from ``sterilot`` and nothing else, so this
list is a promise. A name leaving it is a breaking change and should be a
deliberate one rather than a tidy up that looked harmless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sterilot
from sterilot.store.store import Store

EXPECTED = {
    "Clock",
    "ConfigurationError",
    "ConflictError",
    "IntegrityError",
    "NotFoundError",
    "PolicyError",
    "Settings",
    "SterilotError",
    "ValidationError",
    "__version__",
}


def test_the_exported_names_are_the_ones_promised() -> None:
    assert set(sterilot.__all__) == EXPECTED


def test_every_exported_name_is_really_there() -> None:
    for name in sterilot.__all__:
        assert hasattr(sterilot, name), name


def test_the_version_is_a_release_number() -> None:
    parts = sterilot.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_the_error_types_come_back_as_the_real_ones() -> None:
    for name in ("ValidationError", "NotFoundError", "ConflictError", "PolicyError"):
        found = getattr(sterilot, name)
        assert issubclass(found, sterilot.SterilotError)


def test_the_settings_export_is_the_real_settings() -> None:
    assert sterilot.Settings().facility == "Central Service"


def test_the_store_can_be_opened_without_knowing_where_it_lives(tmp_path: Path) -> None:
    store = sterilot.open_store(str(tmp_path / "sterilot.sqlite3"))
    try:
        assert isinstance(store, Store)
        assert store.up_to_date
    finally:
        store.close()  # type: ignore[attr-defined]


def test_importing_the_package_does_not_pull_in_the_store() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sterilot, sys; print('sterilot.store.store' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_the_package_docstring_says_what_it_is() -> None:
    assert sterilot.__doc__ is not None
    assert "central service" in sterilot.__doc__.lower()


def test_an_unknown_name_is_not_exported() -> None:
    missing = "NotAThing"
    with pytest.raises(AttributeError):
        getattr(sterilot, missing)
