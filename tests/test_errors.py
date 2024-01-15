from __future__ import annotations

import pytest

from sterilot.errors import (
    ConfigurationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    PolicyError,
    SterilotError,
    ValidationError,
    refuse,
    require,
)


def test_message_without_context_is_the_message() -> None:
    err = SterilotError("nothing doing")
    assert str(err) == "nothing doing"
    assert err.context == {}


def test_context_is_appended_in_insertion_order() -> None:
    err = SterilotError("tray is short", tray="ORT-114", missing=2)
    assert str(err) == "tray is short (tray='ORT-114', missing=2)"


def test_context_text_alone() -> None:
    err = SterilotError("x", a=1, b="two")
    assert err.context_text() == "a=1, b='two'"


def test_describe_is_a_plain_dict() -> None:
    err = ValidationError("bad temperature", value=-400)
    assert err.describe() == {
        "code": "validation",
        "message": "bad temperature",
        "context": {"value": -400},
    }


def test_describe_copies_the_context() -> None:
    err = ValidationError("bad", value=1)
    described = err.describe()
    described["context"]["value"] = 2
    assert err.context["value"] == 1


@pytest.mark.parametrize(
    ("cls", "code", "status"),
    [
        (ValidationError, "validation", 2),
        (NotFoundError, "not_found", 3),
        (ConflictError, "conflict", 4),
        (PolicyError, "policy", 5),
        (IntegrityError, "integrity", 6),
        (ConfigurationError, "configuration", 7),
    ],
)
def test_each_subclass_carries_its_own_code_and_status(
    cls: type[SterilotError], code: str, status: int
) -> None:
    err = cls("boom")
    assert err.code == code
    assert err.exit_status == status
    assert isinstance(err, SterilotError)


def test_exit_statuses_are_distinct() -> None:
    classes = [
        SterilotError,
        ValidationError,
        NotFoundError,
        ConflictError,
        PolicyError,
        IntegrityError,
        ConfigurationError,
    ]
    statuses = [cls.exit_status for cls in classes]
    assert len(set(statuses)) == len(statuses)


def test_require_passes_quietly() -> None:
    require(True, "never seen")


def test_require_raises_with_context() -> None:
    with pytest.raises(ValidationError) as caught:
        require(False, "count sheet is empty", tray="ORT-114")
    assert caught.value.context == {"tray": "ORT-114"}


def test_refuse_always_raises() -> None:
    with pytest.raises(PolicyError) as caught:
        refuse("implant load held for the biological", load="A-2201")
    assert caught.value.message == "implant load held for the biological"
    assert caught.value.exit_status == 5
